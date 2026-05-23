from __future__ import annotations

from functools import lru_cache
from typing import Callable

import UnityPy
from UnityPy.enums.BundleFile import ArchiveFlags, CompressionFlags
from UnityPy.helpers.CompressionHelper import DECOMPRESSION_MAP


DEFAULT_UNITYCN_KEY = b"27v8HxLIptguw3Jn"


def _decrypt_control_byte(decryptor, value: int, index: int) -> int:
    sub = decryptor.substitute
    idx = decryptor.index
    mask = (
        sub[index & 3]
        + sub[((index >> 2) & 3) + 4]
        + sub[((index >> 4) & 3) + 8]
        + sub[((index & 0xFF) >> 6) + 12]
    )
    if idx == bytes(range(16)):
        return ((((value & 0xF) - mask) & 0xF) | (((value >> 4) - mask) << 4)) & 0xFF
    return (((idx[value & 0xF] - mask) & 0xF) | ((idx[value >> 4] - mask) << 4)) & 0xFF


def _decode_lz4_with_partial_unitycn(
    decryptor,
    compressed_data: bytes,
    uncompressed_size: int,
    block_index: int,
    decrypt_prefix_size: int,
    write_output: bool,
) -> bytes | bool:
    """Decode Heartopia's UnityCN LZ4 blocks.

    UnityPy/UnityCN-Helper decrypt all LZ4 control bytes, but Heartopia only
    encrypts an initial prefix of each compressed block. The prefix length is
    not exposed by UnityPy, so callers probe for the shortest valid prefix.
    """

    src = memoryview(compressed_data)
    out = bytearray(uncompressed_size) if write_output else None
    source_pos = 0
    target_pos = 0
    sequence_index = block_index

    def control_byte(pos: int, index: int) -> int:
        value = src[pos]
        if pos < decrypt_prefix_size:
            return _decrypt_control_byte(decryptor, value, index)
        return int(value)

    while source_pos < len(src):
        inner_index = sequence_index
        token = control_byte(source_pos, inner_index)
        source_pos += 1
        inner_index += 1

        literal_length = token >> 4
        match_length = token & 0xF

        if literal_length == 0xF:
            while True:
                extra = control_byte(source_pos, inner_index)
                source_pos += 1
                inner_index += 1
                literal_length += extra
                if extra != 0xFF:
                    break

        if source_pos + literal_length > len(src):
            raise ValueError("invalid literal length")
        if target_pos + literal_length > uncompressed_size:
            raise ValueError("literal output overflow")

        if write_output:
            assert out is not None
            out[target_pos : target_pos + literal_length] = src[source_pos : source_pos + literal_length]

        source_pos += literal_length
        target_pos += literal_length

        if source_pos == len(src) and match_length == 0:
            if target_pos != uncompressed_size:
                raise ValueError("output size mismatch")
            return bytes(out) if write_output else True

        if source_pos + 2 > len(src):
            raise ValueError("missing match offset")

        offset = control_byte(source_pos, inner_index)
        offset |= control_byte(source_pos + 1, inner_index + 1) << 8
        source_pos += 2
        inner_index += 2

        if match_length == 0xF:
            while True:
                extra = control_byte(source_pos, inner_index)
                source_pos += 1
                inner_index += 1
                match_length += extra
                if extra != 0xFF:
                    break

        match_length += 4
        if offset <= 0 or offset > target_pos:
            raise ValueError("invalid match offset")
        if target_pos + match_length > uncompressed_size:
            raise ValueError("match output overflow")

        if write_output:
            assert out is not None
            for _ in range(match_length):
                out[target_pos] = out[target_pos - offset]
                target_pos += 1
        else:
            target_pos += match_length

        sequence_index += 1

    raise ValueError("truncated LZ4 block")


@lru_cache(maxsize=4096)
def _probe_threshold_cached(
    decryptor_identity: int,
    compressed_data: bytes,
    uncompressed_size: int,
    block_index: int,
    decryptor,
) -> int:
    # This wrapper is kept cache-compatible by passing bytes; decryptor_identity
    # prevents accidental cache reuse across bundle decryptors.
    del decryptor_identity
    max_probe = min(len(compressed_data), 2048)
    for threshold in range(0, min(161, max_probe + 1)):
        try:
            _decode_lz4_with_partial_unitycn(
                decryptor, compressed_data, uncompressed_size, block_index, threshold, False
            )
            return threshold
        except Exception:
            pass
    for threshold in range(161, max_probe + 1):
        try:
            _decode_lz4_with_partial_unitycn(
                decryptor, compressed_data, uncompressed_size, block_index, threshold, False
            )
            return threshold
        except Exception:
            pass
    raise ValueError(f"unable to determine UnityCN decrypt prefix for block {block_index}")


def _probe_threshold(decryptor, compressed_data: bytes, uncompressed_size: int, block_index: int) -> int:
    return _probe_threshold_cached(id(decryptor), bytes(compressed_data), uncompressed_size, block_index, decryptor)


def install_unitycn_patch(key: bytes | str = DEFAULT_UNITYCN_KEY) -> None:
    """Patch UnityPy's bundle decompressor for Heartopia UnityCN bundles."""

    import importlib

    if isinstance(key, bytes):
        UnityPy.set_assetbundle_decrypt_key(key)
    else:
        UnityPy.set_assetbundle_decrypt_key(key.encode("utf-8"))

    bundle_module = importlib.import_module("UnityPy.files.BundleFile")
    original: Callable = bundle_module.BundleFile.decompress_data

    if getattr(bundle_module.BundleFile.decompress_data, "_heartopia_unitycn_patch", False):
        return

    def patched(self, compressed_data, uncompressed_size, flags, index=0):
        comp_flag = CompressionFlags(flags & ArchiveFlags.CompressionTypeMask)
        if self.decryptor is not None and flags & 0x100 and comp_flag != CompressionFlags.NONE:
            if comp_flag in (CompressionFlags.LZ4, CompressionFlags.LZ4HC):
                threshold = _probe_threshold(self.decryptor, bytes(compressed_data), uncompressed_size, index)
                return _decode_lz4_with_partial_unitycn(
                    self.decryptor,
                    compressed_data,
                    uncompressed_size,
                    index,
                    threshold,
                    True,
                )
            compressed_data = self.decryptor.decrypt_block(compressed_data, index)

        if comp_flag in DECOMPRESSION_MAP:
            return DECOMPRESSION_MAP[comp_flag](compressed_data, uncompressed_size)
        return original(self, compressed_data, uncompressed_size, flags, index)

    patched._heartopia_unitycn_patch = True  # type: ignore[attr-defined]
    bundle_module.BundleFile.decompress_data = patched
