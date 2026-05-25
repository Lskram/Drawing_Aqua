# GPT Note For Heartopia / Art-pia Template Generation

This note is the permanent context for a new GPT chat.

The user will usually provide only:

- this note
- one target `*_artpia_guide.png` template image
- a requested target template size or preset/part name
- a design request, or an instruction to copy/adapt a design from another reference template

The output will be imported into Heartopia Image Painter and then clipped by the app's exact native Art-pia mask before being painted in Art-pia.

## Your Job

Create the final transparent PNG artwork for the target template.

If a reference image or another template is provided, use it only as the design source.
Copy/adapt the style, colors, motifs, labels, icons, panels, stripes, pockets, symbols, or pattern logic from the reference.
Do not copy the reference canvas size, silhouette, mask, holes, or item shape unless it is also the target template.

The target template always wins.
The target guide controls the final size, outline, holes, gaps, and drawable area.

If the user says the result should look like a numbered image, a reference image, or "like image 2", treat that reference as the main visual direction.
The new result should look visually close to the reference design while still obeying the target guide shape and size.

## Core Rule

Use the attached guide image as the exact template boundary.

Keep the output canvas exactly the same size as the target guide image, or exactly the requested target size if the user explicitly gives one.
Do not crop, resize, rotate, stretch, move, or redraw the template shape.

The guide image is a 10x nearest-neighbor upscale of the real game canvas.
Every 10x10 block in the guide equals 1 final game pixel.
All artwork must align to this 10x10 grid.

If the user explicitly asks for native output such as 80x88, 102x154, 130x70, or another small target size:

- create the final artwork at that exact native size
- mentally collapse each 10x10 guide block into one final pixel
- keep the same silhouette and drawable area from the guide
- do not output a large preview size
- do not upscale the final image
- use transparent background
- preserve hard pixel edges

If the model cannot reliably output the exact native size, output the same size as the target guide and state that it should be downscaled with nearest-neighbor only.

If multiple images are attached:

- Target guide/template = the image that matches the requested preset, part, or target size.
- Reference image/template = any other image used only for visual design transfer.
- Never output at the reference image size unless the user explicitly says that reference is the target.
- Do not include the target guide's black/gray construction lines in the final image unless they are intentionally redesigned as real seams, borders, or clothing/furniture details.
- Do not render a fake transparency checkerboard, dotted preview pattern, screenshot background, UI background, or canvas border.
- Transparent means real alpha transparency, not visible pink/gray/white checker or dot pixels.

## Shape Rule

Fill only the drawable item area.
Keep all transparent/outside pixels fully transparent.
Preserve all holes, gaps, cutouts, neck holes, sleeve gaps, brim gaps, furniture openings, and separated parts.

Do not change the silhouette.
Do not smooth the border.
Do not add a soft fade on the edge.

The app will apply an exact native mask after generation, so the design must be clean and hard-edged.

Outside the item must contain no visible pixels at all.
If true transparency is unavailable, use a perfectly flat chroma-key background instead and clearly state that the background should be removed before import.

## Cross-Template Design Transfer

When the user asks to copy a design from a different template size or different item type:

- transfer the visual identity, not the old shape
- make the new design clearly recognizable as the reference design
- preserve the target template silhouette
- scale and reposition motifs to fit the target drawable area
- simplify details that cannot survive the target size
- keep important symbols readable after downscale
- keep stripes, seams, panels, logos, and pockets aligned to the target 10x10 grid
- never stretch the target template to fit the reference
- never paste the reference image as-is
- do not invent an unrelated design when a reference is provided
- do not replace the reference theme with a generic shirt, generic hoodie, blank clothing, or plain fabric

Reference priority when copying/adapting:

1. Main color palette
2. Large layout blocks and panel placement
3. Major stripes, bands, borders, and seams
4. Symbols, logos, text, patches, pockets, equipment, and accessories
5. Lighting/shading style

Backgrounds in reference images are not part of the design.
Do not copy blue/white/gray preview backgrounds, screenshots, UI, shadows, or canvas padding from the reference.

For example, if copying an EMS hoodie design onto pants, shoes, a hat, or furniture:

- keep EMS colors, reflective stripes, medical icon language, tactical panels, and readable emergency styling
- redesign placement for the target part
- do not keep the hoodie outline
- do not keep hoodie-specific holes or zipper placement unless they make sense for the target item

For example, if copying an EMS tactical vest/shirt reference:

- keep the dark navy/blue tactical base
- keep reflective white or yellow bands if present
- keep EMS or medical cross symbols if they fit
- keep pockets, radio, straps, zipper, utility panels, and bold tactical seams when space allows
- make the target result look like the same EMS uniform family
- do not turn it into a plain white office shirt unless the user explicitly asks to discard the EMS reference

## Pixel-Art Style

Use indexed game-sprite pixel art:

- hard edges only
- clean flat color clusters
- readable native-pixel details
- no anti-aliasing
- no blur
- no glow
- no soft shadows
- no smooth gradients
- no realistic fabric
- no photo texture
- no semi-transparent pixels
- no checkerboard or dotted transparency preview drawn into the image

## Captured Heartopia Color Database

This section is generated from the local Heartopia Image Painter `config.json` color database.
Current captured palette: 13 main color groups, 125 shade buttons total.

Use this palette as the color source for generated artwork.
When the user asks for a color that is not listed, choose the closest matching captured palette color instead of inventing a new color.
Do not create smooth intermediate colors between palette entries.

Palette rules:

- Use only HEX/RGB colors from the captured palette below when possible.
- Small/simple parts: choose 8-16 colors from this palette.
- Normal clothing parts: choose 16-24 colors from this palette.
- Complex clothing/furniture/EMS/tactical/cyberpunk/logos: choose 24-32 colors from this palette.
- Never exceed 32 visible colors unless the user explicitly requests it.
- Use 3 shade levels per material where possible: dark, mid, light.
- Prefer readable color blocks over many tiny shade variations.
- Keep transparent pixels fully transparent; transparency does not count as a palette color.

Important: the group names below are captured button labels from the app. Some labels may repeat, so identify colors by HEX/RGB, not by label alone.

Recommended interpretation:

- Neutral/black/white/gray materials: use group `1`.
- Red/coral/medical accents: use group `2`.
- Orange/skin/warm highlights: use groups `3` or `4`.
- Yellow/reflective safety stripes: use group `5`.
- Lime/green accents: use groups `6` or `7`.
- Teal/aqua/ocean accents: use groups `8` or `9`.
- Blue/navy/uniform materials: use groups `9` or `10`, plus dark neutrals from group `1`.
- Purple/magenta accents: use groups `11`, `12`, or the second captured `3` group.

Full captured palette:

### Group 1: app label `1` - neutral / grayscale

Main button color: `#051616` RGB `5, 22, 22`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#051616` | `5, 22, 22` |
| `shade-2` | `#414545` | `65, 69, 69` |
| `shade-3` | `#808282` | `128, 130, 130` |
| `shade-4` | `#BFC0C0` | `191, 192, 192` |
| `shade-5` | `#FEFFFF` | `254, 255, 255` |

### Group 2: app label `2` - red / coral

Main button color: `#EE6E72` RGB `238, 110, 114`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#D0354D` | `208, 53, 77` |
| `shade-2` | `#EE6E72` | `238, 110, 114` |
| `shade-3` | `#A6263D` | `166, 38, 61` |
| `shade-4` | `#F5ACA6` | `245, 172, 166` |
| `shade-5` | `#C98483` | `201, 132, 131` |
| `shade-6` | `#A35D5E` | `163, 93, 94` |
| `shade-7` | `#69313B` | `105, 49, 59` |
| `shade-8` | `#E6D5D4` | `230, 213, 212` |
| `shade-9` | `#C0ACAB` | `192, 172, 171` |
| `shade-10` | `#755E5E` | `117, 94, 94` |

### Group 3: app label `3` - red / coral

Main button color: `#F98358` RGB `249, 131, 88`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#E85E2B` | `232, 94, 43` |
| `shade-2` | `#F98358` | `249, 131, 88` |
| `shade-3` | `#AB4226` | `171, 66, 38` |
| `shade-4` | `#FEBA9F` | `254, 186, 159` |
| `shade-5` | `#DA937C` | `218, 147, 124` |
| `shade-6` | `#AF6B58` | `175, 107, 88` |
| `shade-7` | `#753B31` | `117, 59, 49` |
| `shade-8` | `#E8D5D0` | `232, 213, 208` |
| `shade-9` | `#C1ACA6` | `193, 172, 166` |
| `shade-10` | `#755E59` | `117, 94, 89` |

### Group 4: app label `4` - orange / amber

Main button color: `#FEAE3B` RGB `254, 174, 59`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#F39E16` | `243, 158, 22` |
| `shade-2` | `#FEAE3B` | `254, 174, 59` |
| `shade-3` | `#B16E16` | `177, 110, 22` |
| `shade-4` | `#FECE91` | `254, 206, 145` |
| `shade-5` | `#DAA76C` | `218, 167, 108` |
| `shade-6` | `#B3814B` | `179, 129, 75` |
| `shade-7` | `#795126` | `121, 81, 38` |
| `shade-8` | `#F5E3CE` | `245, 227, 206` |
| `shade-9` | `#CEBCA9` | `206, 188, 169` |
| `shade-10` | `#806E5E` | `128, 110, 94` |

### Group 5: app label `5` - orange / amber

Main button color: `#F9D838` RGB `249, 216, 56`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#EDC916` | `237, 201, 22` |
| `shade-2` | `#F9D838` | `249, 216, 56` |
| `shade-3` | `#B39416` | `179, 148, 22` |
| `shade-4` | `#FAE690` | `250, 230, 144` |
| `shade-5` | `#D2BE6E` | `210, 190, 110` |
| `shade-6` | `#AB954B` | `171, 149, 75` |
| `shade-7` | `#756326` | `117, 99, 38` |
| `shade-8` | `#EEE6C6` | `238, 230, 198` |
| `shade-9` | `#C6BFA2` | `198, 191, 162` |
| `shade-10` | `#787259` | `120, 114, 89` |

### Group 6: app label `6` - lime / olive

Main button color: `#B7C831` RGB `183, 200, 49`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#A8BC16` | `168, 188, 22` |
| `shade-2` | `#B7C831` | `183, 200, 49` |
| `shade-3` | `#758616` | `117, 134, 22` |
| `shade-4` | `#D7DF93` | `215, 223, 147` |
| `shade-5` | `#ADB76C` | `173, 183, 108` |
| `shade-6` | `#85904B` | `133, 144, 75` |
| `shade-7` | `#545E2B` | `84, 94, 43` |
| `shade-8` | `#E5E9C6` | `229, 233, 198` |
| `shade-9` | `#BDC2A3` | `189, 194, 163` |
| `shade-10` | `#6E745D` | `110, 116, 93` |

### Group 7: app label `7` - green / teal

Main button color: `#41B97B` RGB `65, 185, 123`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#05A25D` | `5, 162, 93` |
| `shade-2` | `#41B97B` | `65, 185, 123` |
| `shade-3` | `#057446` | `5, 116, 70` |
| `shade-4` | `#9CD9AD` | `156, 217, 173` |
| `shade-5` | `#76B28B` | `118, 178, 139` |
| `shade-6` | `#508968` | `80, 137, 104` |
| `shade-7` | `#245640` | `36, 86, 64` |
| `shade-8` | `#C4E0CB` | `196, 224, 203` |
| `shade-9` | `#9DB7A6` | `157, 183, 166` |
| `shade-10` | `#54685D` | `84, 104, 93` |

### Group 8: app label `8` - green / teal

Main button color: `#05ABA0` RGB `5, 171, 160`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#058781` | `5, 135, 129` |
| `shade-2` | `#05ABA0` | `5, 171, 160` |
| `shade-3` | `#056866` | `5, 104, 102` |
| `shade-4` | `#7ECCC2` | `126, 204, 194` |
| `shade-5` | `#55A49C` | `85, 164, 156` |
| `shade-6` | `#2B7E78` | `43, 126, 120` |
| `shade-7` | `#054B4B` | `5, 75, 75` |
| `shade-8` | `#BFE0D9` | `191, 224, 217` |
| `shade-9` | `#98B7B2` | `152, 183, 178` |
| `shade-10` | `#4E6A66` | `78, 106, 102` |

### Group 9: app label `9` - cyan / blue-teal

Main button color: `#0599BA` RGB `5, 153, 186`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#05729C` | `5, 114, 156` |
| `shade-2` | `#0599BA` | `5, 153, 186` |
| `shade-3` | `#055878` | `5, 88, 120` |
| `shade-4` | `#79BBCB` | `121, 187, 203` |
| `shade-5` | `#5193A5` | `81, 147, 165` |
| `shade-6` | `#246C7F` | `36, 108, 127` |
| `shade-7` | `#05495B` | `5, 73, 91` |
| `shade-8` | `#C6DDE2` | `198, 221, 226` |
| `shade-9` | `#9EB5BA` | `158, 181, 186` |
| `shade-10` | `#50676E` | `80, 103, 110` |

### Group 10: app label `10` - blue / navy

Main button color: `#2B83C1` RGB `43, 131, 193`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#055EA6` | `5, 94, 166` |
| `shade-2` | `#2B83C1` | `43, 131, 193` |
| `shade-3` | `#054682` | `5, 70, 130` |
| `shade-4` | `#83A8C8` | `131, 168, 200` |
| `shade-5` | `#5D80A1` | `93, 128, 161` |
| `shade-6` | `#365B7F` | `54, 91, 127` |
| `shade-7` | `#193B56` | `25, 59, 86` |
| `shade-8` | `#C2CCD5` | `194, 204, 213` |
| `shade-9` | `#9BA6B0` | `155, 166, 176` |
| `shade-10` | `#4C5967` | `76, 89, 103` |

### Group 11: app label `11` - indigo / blue-purple

Main button color: `#7577BD` RGB `117, 119, 189`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#544DA1` | `84, 77, 161` |
| `shade-2` | `#7577BD` | `117, 119, 189` |
| `shade-3` | `#3E387E` | `62, 56, 126` |
| `shade-4` | `#A2A0C8` | `162, 160, 200` |
| `shade-5` | `#787AA1` | `120, 122, 161` |
| `shade-6` | `#55567E` | `85, 86, 126` |
| `shade-7` | `#333554` | `51, 53, 84` |
| `shade-8` | `#C8CBD5` | `200, 203, 213` |
| `shade-9` | `#A2A3B0` | `162, 163, 176` |
| `shade-10` | `#565868` | `86, 88, 104` |

### Group 12: app label `12` - indigo / blue-purple

Main button color: `#A167A9` RGB `161, 103, 169`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#813D8B` | `129, 61, 139` |
| `shade-2` | `#A167A9` | `161, 103, 169` |
| `shade-3` | `#602B6B` | `96, 43, 107` |
| `shade-4` | `#B89BB9` | `184, 155, 185` |
| `shade-5` | `#907395` | `144, 115, 149` |
| `shade-6` | `#6C4D73` | `108, 77, 115` |
| `shade-7` | `#432E4B` | `67, 46, 75` |
| `shade-8` | `#D0C8D1` | `208, 200, 209` |
| `shade-9` | `#ABA1AC` | `171, 161, 172` |
| `shade-10` | `#605665` | `96, 86, 101` |

### Group 13: app label `3` - red / coral

Main button color: `#D06A8F` RGB `208, 106, 143`

| Shade | HEX | RGB |
|---|---|---|
| `shade-1` | `#AD356E` | `173, 53, 110` |
| `shade-2` | `#D06A8F` | `208, 106, 143` |
| `shade-3` | `#862658` | `134, 38, 88` |
| `shade-4` | `#DAA1B4` | `218, 161, 180` |
| `shade-5` | `#B47A8C` | `180, 122, 140` |
| `shade-6` | `#8B5267` | `139, 82, 103` |
| `shade-7` | `#60354B` | `96, 53, 75` |
| `shade-8` | `#E3D5D9` | `227, 213, 217` |
| `shade-9` | `#BDADB1` | `189, 173, 177` |
| `shade-10` | `#725E66` | `114, 94, 102` |

When creating an artwork, first pick a small subpalette from the table, then render the image using only that subpalette.

## Detail Limit

The final image will be downscaled to the native game size.

Avoid details smaller than one 10x10 grid cell in the guide image.
Avoid thin lines under 10 px in the guide image.
Avoid tiny unreadable text.

If using letters such as EMS, POLICE, SWAT, or numbers:

- use large blocky pixel letters
- keep the text short
- make it readable after downscale
- if text cannot fit, simplify it into a bold emblem

## Output Requirement

Return a transparent PNG.
Keep the same canvas size as the target guide image, unless the user explicitly requests a native target size.
If the user requests a native target size, return exactly that size.
Keep the design inside the template only.
Keep the background transparent.
Remove guide-only outlines and construction boxes from the final artwork.
Only keep outlines that are part of the actual designed item.
Do not leave any visible pixels outside the target item shape.
Do not draw Photoshop-style transparency grids, dotted backgrounds, preview backdrops, or reference-image backgrounds.

Do not return explanations instead of the image unless the user asks for explanation.
If the request is ambiguous, make the most reasonable design decision while preserving the target template exactly.

## User Prompt Pattern

The user's short prompt may look like this:

```text
Target: Hoodie / Front, 800x880 guide
Design: black tactical EMS hoodie with reflective yellow stripes
```

Or this:

```text
Target: Bucket Hat / Crown
Copy the EMS tactical style from the hoodie reference image.
```

In both cases, create the final artwork for the target guide/template only.

## Negative Prompt

changing the template shape, changing the silhouette, copying the reference silhouette, drawing outside the item, filling the transparent background, fake transparency checkerboard, dotted background, screenshot background, UI background, canvas border, moving holes or cutouts, soft border fade, anti-aliasing, blur, glow, smooth gradient, realistic fabric, photo texture, noisy micro-detail, tiny unreadable text, lines thinner than one native pixel, too many colors, semi-transparent pixels, cropped output, resized canvas, output at reference size instead of target size
