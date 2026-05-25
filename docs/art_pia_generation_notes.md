# Heartopia Art-pia Generation Notes

บันทึกนี้ใช้สำหรับเจนภาพให้ตรงกับขนาด part จริงของ Heartopia ก่อนนำเข้าโปรแกรมวาด
เป้าหมายคือให้ภาพคมที่สุด โดยไม่ทำให้ระบบเดิมของโปรแกรมเปลี่ยนพฤติกรรม

## Current App Settings

ค่าจาก `config.json` ณ ตอนทำ note นี้:

| Setting | Value |
|---|---:|
| Captured main colors | 13 |
| Captured shades | 125 |
| Image fit mode | Smart |
| Auto crop | Off |
| Map preview to captured palette | On |
| Dither | Off |
| Paint mode | color |
| Bucket-fill most-used color first | On |
| Bucket-fill large regions | On |

หมายเหตุ: main color ชื่อ `3` มี 2 ชุดใน config แต่โปรแกรมแยกด้วยตำแหน่งปุ่มแล้ว ไม่ได้แยกด้วยชื่ออย่างเดียว

## Best Workflow

1. เลือก preset และ part ในตารางด้านล่าง
2. เจนหรือ export ภาพให้เป็นขนาดจริงของ part นั้น เช่น `Hoodie / Front = 80x88`
3. ใช้ PNG ที่ขนาด native จริง ไม่ต้อง upscale ก่อน import เข้าโปรแกรม
4. ใช้ pixel art hard-edge เท่านั้น
5. ปิด anti-alias, blur, smooth gradient, soft shadow
6. จำกัดจำนวนสีตามตาราง ไม่จำเป็นต้องใช้สีเยอะสุดเสมอ
7. ในโปรแกรมให้เปิด `Map preview to captured palette` และปิด `Dither`

ถ้าภาพมีขนาดตรงกับ part จริงตั้งแต่แรก รายละเอียดจะไม่หายจากการย่อภาพขนาดใหญ่ลงมา

## Exact Art-pia Guide Workflow

ใช้ขั้นตอนนี้แทนการแคปหน้าจอ เพราะการแคปจะติด zoom/padding/anti-alias และขนาดจะไม่ตรง 100%

1. ในโปรแกรมเลือก preset และ part เช่น `Hoodie / Front`
2. กด `Export Art-pia GPT guide...`
3. โปรแกรมจะสร้าง 2 ไฟล์:
   - `*_artpia_guide.png` เป็นไฟล์ 10x มีเส้นโครงชัดสำหรับส่งให้ GPT
   - `*_artpia_mask.png` เป็น mask native size สำหรับ clip ภาพกลับเข้าทรงจริง
4. ส่ง `*_artpia_guide.png` ให้ GPT แล้วสั่งให้เติมลวดลายเฉพาะพื้นที่สีขาว/ในโครง
5. เมื่อเอาภาพกลับเข้าโปรแกรม ให้ติ๊ก `Clip imported image to Art-pia exact mask`
6. โปรแกรมจะตัดภาพด้วย mask จริงอีกครั้งก่อนวาด ถึงแม้ GPT จะวาดเกินขอบ

สำคัญ: ไฟล์ guide ใช้สำหรับให้ GPT เห็นโครง แต่ mask native size คือกฎสุดท้ายของโปรแกรม

## GPT Attachment Rules

แนบส่วนนี้ให้ GPT ทุกครั้งพร้อมไฟล์ `*_artpia_guide.png`

```text
You are editing a Heartopia / Art-pia pixel-art template.

Use the attached guide image as the exact template boundary.
Keep the output canvas exactly the same size as the attached guide image.
Do not crop, resize, rotate, stretch, move, or redraw the template shape.

The guide is a 10x nearest-neighbor upscale of the real game canvas.
Every 10x10 block in the guide equals 1 final game pixel.
All seams, stripes, symbols, panels, icons, pockets, highlights, and pattern edges must align to this 10x10 grid.
Avoid details smaller than one 10x10 grid cell.

Fill only the drawable item area.
Keep all transparent/outside pixels fully transparent.
Preserve all holes and cutouts such as neck holes, sleeve gaps, brim gaps, furniture openings, and separated parts.
The final app will apply an exact mask, so do not rely on soft fading at the border.

Use indexed pixel-art style:
- hard edges only
- flat color clusters
- crisp 1-pixel native detail
- no anti-aliasing
- no blur
- no glow
- no soft shadow
- no smooth gradient
- no realistic fabric or photo texture

Color limit:
- Use 16 colors for simple items or small parts.
- Use 24 colors for normal clothing parts.
- Use 32 colors maximum for complex designs such as EMS, police, tactical, cyberpunk, furniture panels, or detailed logos.
- Never use more than 32 colors unless explicitly requested.
- Use 3 shade levels per major material: dark, mid, light.
- Prefer clean readable shapes over many tiny color variations.

The image must remain readable after nearest-neighbor downscale to the native game size.
```

Negative prompt:

```text
changing the template shape, changing the silhouette, drawing outside the item, filling transparent background,
moving holes or cutouts, soft border fade, anti-aliasing, blur, glow, smooth gradient, realistic fabric,
photo texture, noisy micro-detail, tiny unreadable text, lines thinner than one native pixel,
too many colors, semi-transparent pixels, cropped output, resized canvas
```

สำหรับงานที่ต้องมีโลโก้/ตัวอักษร เช่น EMS ให้เพิ่ม:

```text
If using letters or symbols, make them large blocky pixel letters.
Do not use tiny text.
Keep each letter readable after downscale.
If the text cannot fit clearly, simplify it into a bold emblem instead.
```

## Prompt Template

ใช้ template นี้แล้วแทนค่า `{PRESET}`, `{PART}`, `{WIDTH}`, `{HEIGHT}`, `{COLOR_LIMIT}`

```text
Create a {WIDTH}x{HEIGHT} transparent PNG pixel-art asset for Heartopia {PRESET}, {PART}.
Use the exact native canvas size {WIDTH}x{HEIGHT}. Pixel-perfect hard edges only.
Use {COLOR_LIMIT} colors maximum, selected from the Heartopia captured palette.
No anti-aliasing, no blur, no soft shadow, no smooth gradient, no photorealism.
Use clean pixel clusters, readable silhouette, 1-pixel crisp details, indexed-color game sprite style.
Keep the design centered and fitted to the drawable template. Do not upscale.
```

Negative prompt:

```text
anti-aliasing, smooth edges, blur, soft shadow, gradient, glow, realistic fabric, photographic detail,
4k, high resolution render, painterly, watercolor, airbrush, noise, tiny unreadable details
```

ถ้าเครื่องมือเจนภาพไม่ยอมสร้างขนาดเล็กโดยตรง ให้เจนที่สเกลคูณจำนวนเต็ม เช่น 4x หรือ 8x แล้วลดกลับด้วย nearest-neighbor เท่านั้น

## Template Overlay Prompt

ใช้ส่วนนี้เมื่อมีไฟล์ template/mask อยู่แล้ว และต้องการเติมลวดลายลงไปในพื้นที่ของเสื้อโดยไม่เปลี่ยนทรง

สำหรับไฟล์ `C:\Users\UsEr\Downloads\Templaet Hooddie Front.png`:

| Item | Value |
|---|---:|
| Template size | 800x880 |
| Target game size | 80x88 |
| Scale | 10x |
| Preset / part | Hoodie / Front |
| Recommended colors | 24-32 |

ถ้าใช้ไฟล์ template 800x880 เป็น reference ให้สั่งว่า output ยังเป็น 800x880 แต่ทุกลายต้อง align กับ grid 10x10 px เพราะสุดท้ายต้องลดกลับเป็น 80x88 ด้วย nearest-neighbor

```text
Use the provided image as an exact Hoodie Front template mask.
Keep the same canvas size, 800x880 transparent PNG.
Fill only the white hoodie area with the requested design. Keep all transparent pixels fully transparent.
Do not change the hoodie silhouette, arm openings, shoulder shape, hem, or neck hole.

The final game asset is 80x88, so treat this 800x880 image as a 10x upscale.
All pattern edges, outlines, seams, symbols, and color blocks must align to a 10x10 pixel grid.
Minimum visible detail size is 10 pixels wide. Do not create sub-pixel detail.

Use 24-32 colors maximum from the Heartopia captured palette.
Use hard pixel-art edges only. No anti-aliasing, no blur, no soft shadow, no smooth gradient.
Make the design readable after nearest-neighbor downscale to 80x88.
```

เติมคำอธิบายลายต่อท้าย เช่น:

```text
Design: black cyberpunk hoodie with cyan circuit lines, small chest emblem, subtle dark-blue panels, clean pixel clusters.
```

Negative prompt สำหรับ template overlay:

```text
changing the template shape, drawing outside the hoodie mask, filling the transparent background,
smooth fabric rendering, realistic wrinkles, soft shadows, tiny text, thin lines under 10 pixels,
anti-aliasing, gradient, blur, glow, high-detail texture
```

ถ้าเครื่องมือรองรับ output 80x88 โดยตรง ให้ใช้ prompt นี้แทน:

```text
Create an exact 80x88 transparent PNG for Heartopia Hoodie Front using the provided hoodie template as the mask.
Fill only the hoodie area. Preserve the neck hole and transparent outside area.
Use 24-32 colors maximum from the Heartopia captured palette.
Pixel-perfect hard edges only, no anti-aliasing, no blur, no gradient.
The design must remain readable at native 80x88 size.
```

## Color Count Guide

| Pixel area | Recommended colors |
|---:|---:|
| under 2,500 cells | 8-12 |
| 2,500-6,000 cells | 12-24 |
| 6,000-10,000 cells | 24-32 |
| 10,000-20,000 cells | 32-48 |
| over 20,000 cells | 48-64 |

หลักคิด: ขนาดเล็กเกินไปไม่ควรใช้สีเยอะ เพราะสีจะกลายเป็นจุดรบกวนแทนรายละเอียด

## Preset And Part Sizes

| Preset | Part | Size | Area | Suggested colors | Size instruction |
|---|---|---:|---:|---:|---|
| T-Shirt | Front | 64x80 | 5,120 | 16-24 | exact 64x80 transparent PNG |
| T-Shirt | Back | 64x80 | 5,120 | 16-24 | exact 64x80 transparent PNG |
| T-Shirt | Left Sleeve | 64x48 | 3,072 | 12-16 | exact 64x48 transparent PNG |
| T-Shirt | Right Sleeve | 64x48 | 3,072 | 12-16 | exact 64x48 transparent PNG |
| Tank Top | Front | 64x64 | 4,096 | 16-24 | exact 64x64 transparent PNG |
| Tank Top | Back | 64x64 | 4,096 | 16-24 | exact 64x64 transparent PNG |
| Mini Skirt | Front | 128x64 | 8,192 | 24-32 | exact 128x64 transparent PNG |
| Mini Skirt | Back | 128x64 | 8,192 | 24-32 | exact 128x64 transparent PNG |
| Shorts | Front | 102x64 | 6,528 | 24-32 | exact 102x64 transparent PNG |
| Shorts | Back | 102x64 | 6,528 | 24-32 | exact 102x64 transparent PNG |
| Bucket Hat | Front Brim | 126x78 | 9,828 | 24-32 | exact 126x78 transparent PNG |
| Bucket Hat | Back Brim | 126x78 | 9,828 | 24-32 | exact 126x78 transparent PNG |
| Bucket Hat | Crown | 100x100 | 10,000 | 24-32 | exact 100x100 transparent PNG |
| Hoodie | Front | 80x88 | 7,040 | 24-32 | exact 80x88 transparent PNG |
| Hoodie | Back | 80x88 | 7,040 | 24-32 | exact 80x88 transparent PNG |
| Hoodie | Sleeve | 130x70 | 9,100 | 24-32 | exact 130x70 transparent PNG |
| Pants | Front | 80x116 | 9,280 | 24-32 | exact 80x116 transparent PNG |
| Pants | Back | 80x116 | 9,280 | 24-32 | exact 80x116 transparent PNG |
| Dress | Front | 102x154 | 15,708 | 32-48 | exact 102x154 transparent PNG |
| Dress | Back | 76x154 | 11,704 | 32-48 | exact 76x154 transparent PNG |
| Dress | Innerwear | 168x102 | 17,136 | 32-48 | exact 168x102 transparent PNG |
| Baseball Cap | Front | 54x60 | 3,240 | 12-16 | exact 54x60 transparent PNG |
| Baseball Cap | Back and Side | 128x62 | 7,936 | 24-32 | exact 128x62 transparent PNG |
| Baseball Cap | Brim | 62x52 | 3,224 | 12-16 | exact 62x52 transparent PNG |
| Canvas Shoes | Upper | 100x90 | 9,000 | 24-32 | exact 100x90 transparent PNG |
| Canvas Shoes | Toe and Laces | 120x60 | 7,200 | 24-32 | exact 120x60 transparent PNG |
| Canvas Shoes | Sole | 60x60 | 3,600 | 16-24 | exact 60x60 transparent PNG |
| Mary Jane Shoes | Upper | 78x64 | 4,992 | 16-24 | exact 78x64 transparent PNG |
| Mary Jane Shoes | Sole | 108x64 | 6,912 | 24-32 | exact 108x64 transparent PNG |
| Wooden Single Bed | Quilt | 200x130 | 26,000 | 48-64 | exact 200x130 transparent PNG |
| Wooden Single Bed | Bed Frame | 200x98 | 19,600 | 32-48 | exact 200x98 transparent PNG |
| Wooden Double Bed | Quilt | 256x128 | 32,768 | 48-64 | exact 256x128 transparent PNG |
| Wooden Double Bed | Bed Frame | 256x110 | 28,160 | 48-64 | exact 256x110 transparent PNG |
| Wooden Wardrobe | Cabinet Doors | 128x128 | 16,384 | 32-48 | exact 128x128 transparent PNG |
| Wooden Nightstand | Cabinet Front | 128x128 | 16,384 | 32-48 | exact 128x128 transparent PNG |
| Wooden Table Lamp | Lampshade Front | 80x46 | 3,680 | 16-24 | exact 80x46 transparent PNG |
| Wooden Table Lamp | Lampshade Back | 80x46 | 3,680 | 16-24 | exact 80x46 transparent PNG |
| Wooden Table Lamp | Base Edge | 128x28 | 3,584 | 16-24 | exact 128x28 transparent PNG |
| Wooden Chair | Chair Back Front | 54x28 | 1,512 | 8-12 | exact 54x28 transparent PNG |
| Wooden Chair | Chair Back Back | 54x28 | 1,512 | 8-12 | exact 54x28 transparent PNG |
| Wooden Chair | Seat Surface | 54x54 | 2,916 | 12-16 | exact 54x54 transparent PNG |
| Wooden Tea Table | Table Top | 128x128 | 16,384 | 32-48 | exact 128x128 transparent PNG |
| Wooden Loveseat | Sofa Back | 200x110 | 22,000 | 48-64 | exact 200x110 transparent PNG |
| Wooden Loveseat | Sofa Seat | 200x110 | 22,000 | 48-64 | exact 200x110 transparent PNG |
| Wooden Armchair | Sofa Back | 60x60 | 3,600 | 16-24 | exact 60x60 transparent PNG |
| Wooden Armchair | Sofa Seat | 60x70 | 4,200 | 16-24 | exact 60x70 transparent PNG |
| Wooden Floor Lamp | Lampshade Front | 80x52 | 4,160 | 16-24 | exact 80x52 transparent PNG |
| Wooden Floor Lamp | Lampshade Back | 80x52 | 4,160 | 16-24 | exact 80x52 transparent PNG |
| Wooden Floor Lamp | Base Edge | 128x16 | 2,048 | 8-12 | exact 128x16 transparent PNG |
| Christmas Stocking | Front | 64x72 | 4,608 | 16-24 | exact 64x72 transparent PNG |
| Christmas Stocking | Back | 64x72 | 4,608 | 16-24 | exact 64x72 transparent PNG |
| Painted Egg | Front | 30x40 | 1,200 | 8-12 | exact 30x40 transparent PNG |
| Painted Egg | Back | 30x40 | 1,200 | 8-12 | exact 30x40 transparent PNG |

## Captured Palette

ใช้สีด้านล่างเป็น palette อ้างอิงในการเจนภาพหรือปรับสี ภาพสุดท้ายในโปรแกรมจะถูกเลือกเป็น shade ที่ใกล้ที่สุดกับสีเหล่านี้

### Main 1 `#051616`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#051616` | `5,22,22` |
| shade-2 | `#414545` | `65,69,69` |
| shade-3 | `#808282` | `128,130,130` |
| shade-4 | `#BFC0C0` | `191,192,192` |
| shade-5 | `#FEFFFF` | `254,255,255` |

### Main 2 `#EE6E72`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#D0354D` | `208,53,77` |
| shade-2 | `#EE6E72` | `238,110,114` |
| shade-3 | `#A6263D` | `166,38,61` |
| shade-4 | `#F5ACA6` | `245,172,166` |
| shade-5 | `#C98483` | `201,132,131` |
| shade-6 | `#A35D5E` | `163,93,94` |
| shade-7 | `#69313B` | `105,49,59` |
| shade-8 | `#E6D5D4` | `230,213,212` |
| shade-9 | `#C0ACAB` | `192,172,171` |
| shade-10 | `#755E5E` | `117,94,94` |

### Main 3 Orange `#F98358`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#E85E2B` | `232,94,43` |
| shade-2 | `#F98358` | `249,131,88` |
| shade-3 | `#AB4226` | `171,66,38` |
| shade-4 | `#FEBA9F` | `254,186,159` |
| shade-5 | `#DA937C` | `218,147,124` |
| shade-6 | `#AF6B58` | `175,107,88` |
| shade-7 | `#753B31` | `117,59,49` |
| shade-8 | `#E8D5D0` | `232,213,208` |
| shade-9 | `#C1ACA6` | `193,172,166` |
| shade-10 | `#755E59` | `117,94,89` |

### Main 4 `#FEAE3B`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#F39E16` | `243,158,22` |
| shade-2 | `#FEAE3B` | `254,174,59` |
| shade-3 | `#B16E16` | `177,110,22` |
| shade-4 | `#FECE91` | `254,206,145` |
| shade-5 | `#DAA76C` | `218,167,108` |
| shade-6 | `#B3814B` | `179,129,75` |
| shade-7 | `#795126` | `121,81,38` |
| shade-8 | `#F5E3CE` | `245,227,206` |
| shade-9 | `#CEBCA9` | `206,188,169` |
| shade-10 | `#806E5E` | `128,110,94` |

### Main 5 `#F9D838`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#EDC916` | `237,201,22` |
| shade-2 | `#F9D838` | `249,216,56` |
| shade-3 | `#B39416` | `179,148,22` |
| shade-4 | `#FAE690` | `250,230,144` |
| shade-5 | `#D2BE6E` | `210,190,110` |
| shade-6 | `#AB954B` | `171,149,75` |
| shade-7 | `#756326` | `117,99,38` |
| shade-8 | `#EEE6C6` | `238,230,198` |
| shade-9 | `#C6BFA2` | `198,191,162` |
| shade-10 | `#787259` | `120,114,89` |

### Main 6 `#B7C831`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#A8BC16` | `168,188,22` |
| shade-2 | `#B7C831` | `183,200,49` |
| shade-3 | `#758616` | `117,134,22` |
| shade-4 | `#D7DF93` | `215,223,147` |
| shade-5 | `#ADB76C` | `173,183,108` |
| shade-6 | `#85904B` | `133,144,75` |
| shade-7 | `#545E2B` | `84,94,43` |
| shade-8 | `#E5E9C6` | `229,233,198` |
| shade-9 | `#BDC2A3` | `189,194,163` |
| shade-10 | `#6E745D` | `110,116,93` |

### Main 7 `#41B97B`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#05A25D` | `5,162,93` |
| shade-2 | `#41B97B` | `65,185,123` |
| shade-3 | `#057446` | `5,116,70` |
| shade-4 | `#9CD9AD` | `156,217,173` |
| shade-5 | `#76B28B` | `118,178,139` |
| shade-6 | `#508968` | `80,137,104` |
| shade-7 | `#245640` | `36,86,64` |
| shade-8 | `#C4E0CB` | `196,224,203` |
| shade-9 | `#9DB7A6` | `157,183,166` |
| shade-10 | `#54685D` | `84,104,93` |

### Main 8 `#05ABA0`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#058781` | `5,135,129` |
| shade-2 | `#05ABA0` | `5,171,160` |
| shade-3 | `#056866` | `5,104,102` |
| shade-4 | `#7ECCC2` | `126,204,194` |
| shade-5 | `#55A49C` | `85,164,156` |
| shade-6 | `#2B7E78` | `43,126,120` |
| shade-7 | `#054B4B` | `5,75,75` |
| shade-8 | `#BFE0D9` | `191,224,217` |
| shade-9 | `#98B7B2` | `152,183,178` |
| shade-10 | `#4E6A66` | `78,106,102` |

### Main 9 `#0599BA`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#05729C` | `5,114,156` |
| shade-2 | `#0599BA` | `5,153,186` |
| shade-3 | `#055878` | `5,88,120` |
| shade-4 | `#79BBCB` | `121,187,203` |
| shade-5 | `#5193A5` | `81,147,165` |
| shade-6 | `#246C7F` | `36,108,127` |
| shade-7 | `#05495B` | `5,73,91` |
| shade-8 | `#C6DDE2` | `198,221,226` |
| shade-9 | `#9EB5BA` | `158,181,186` |
| shade-10 | `#50676E` | `80,103,110` |

### Main 10 `#2B83C1`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#055EA6` | `5,94,166` |
| shade-2 | `#2B83C1` | `43,131,193` |
| shade-3 | `#054682` | `5,70,130` |
| shade-4 | `#83A8C8` | `131,168,200` |
| shade-5 | `#5D80A1` | `93,128,161` |
| shade-6 | `#365B7F` | `54,91,127` |
| shade-7 | `#193B56` | `25,59,86` |
| shade-8 | `#C2CCD5` | `194,204,213` |
| shade-9 | `#9BA6B0` | `155,166,176` |
| shade-10 | `#4C5967` | `76,89,103` |

### Main 11 `#7577BD`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#544DA1` | `84,77,161` |
| shade-2 | `#7577BD` | `117,119,189` |
| shade-3 | `#3E387E` | `62,56,126` |
| shade-4 | `#A2A0C8` | `162,160,200` |
| shade-5 | `#787AA1` | `120,122,161` |
| shade-6 | `#55567E` | `85,86,126` |
| shade-7 | `#333554` | `51,53,84` |
| shade-8 | `#C8CBD5` | `200,203,213` |
| shade-9 | `#A2A3B0` | `162,163,176` |
| shade-10 | `#565868` | `86,88,104` |

### Main 12 `#A167A9`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#813D8B` | `129,61,139` |
| shade-2 | `#A167A9` | `161,103,169` |
| shade-3 | `#602B6B` | `96,43,107` |
| shade-4 | `#B89BB9` | `184,155,185` |
| shade-5 | `#907395` | `144,115,149` |
| shade-6 | `#6C4D73` | `108,77,115` |
| shade-7 | `#432E4B` | `67,46,75` |
| shade-8 | `#D0C8D1` | `208,200,209` |
| shade-9 | `#ABA1AC` | `171,161,172` |
| shade-10 | `#605665` | `96,86,101` |

### Main 3 Pink `#D06A8F`

| Shade | Hex | RGB |
|---|---|---|
| shade-1 | `#AD356E` | `173,53,110` |
| shade-2 | `#D06A8F` | `208,106,143` |
| shade-3 | `#862658` | `134,38,88` |
| shade-4 | `#DAA1B4` | `218,161,180` |
| shade-5 | `#B47A8C` | `180,122,140` |
| shade-6 | `#8B5267` | `139,82,103` |
| shade-7 | `#60354B` | `96,53,75` |
| shade-8 | `#E3D5D9` | `227,213,217` |
| shade-9 | `#BDADB1` | `189,173,177` |
| shade-10 | `#725E66` | `114,94,102` |

## Quick Copy Examples

Hoodie Front:

```text
Create an 80x88 transparent PNG pixel-art asset for Heartopia Hoodie, Front.
Use exact native canvas size 80x88. Use 24-32 colors maximum from the Heartopia captured palette.
Hard edges only, no anti-aliasing, no blur, no gradient, no soft shadow.
```

Dress Front:

```text
Create a 102x154 transparent PNG pixel-art asset for Heartopia Dress, Front.
Use exact native canvas size 102x154. Use 32-48 colors maximum from the Heartopia captured palette.
Hard edges only, clean pixel clusters, readable clothing silhouette, no anti-aliasing.
```

Wooden Double Bed Quilt:

```text
Create a 256x128 transparent PNG pixel-art asset for Heartopia Wooden Double Bed, Quilt.
Use exact native canvas size 256x128. Use 48-64 colors maximum from the Heartopia captured palette.
Hard edges only, no blur, no smooth gradient, no photorealistic texture.
```
