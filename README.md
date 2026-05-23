# Heartopia Image Painter

A small desktop GUI that helps you “paint” an image into **Heartopia** by:

- Resizing your image to a supported in-game canvas grid
- Letting you select the on-screen canvas area with a translucent preview overlay
- Clicking the correct palette buttons (main color → shade) and then clicking each pixel

This app uses on-screen overlays for picking points/areas and uses mouse automation to do the painting.

## Features

- Import any image and resize it to a preset grid
- On-screen **canvas area selection** with translucent preview
- Guided **palette setup wizard** (captures button positions and samples their RGB)
- Adjustable **timing / reliability** controls (useful if clicks don’t register)
- Optional **bucket-fill most-used color** speed boost (requires capturing Paint tool + Bucket tool button positions)
- Game-derived multi-part presets from Heartopia `DrawCustom` / `DrawSegment` tables (each part remembers its own image + canvas area)
- Persistent settings saved to `config.json`

## Requirements

- Windows (recommended; this is what it’s been tested on)
- Python 3.11+ (a recent Python is recommended)

## Install (Windows / PowerShell)

Video Tutorial:
https://www.youtube.com/watch?v=WgcFCH_MMPs

From the repo folder:

1. Create a virtual environment:

	- `py -m venv .venv`

2. Activate it:

	- `./.venv/Scripts/Activate.ps1`

3. Install dependencies:

	- `pip install -r requirements.txt`

## Run

- `python main.py`

## Presets

| Preset | Part / Precision | Size |
|---|---|---:|
| 1:1 | Small | 30×30 |
| 1:1 | Medium | 50×50 |
| 1:1 | Big | 100×100 |
| 1:1 | Super Large | 150×150 |
| 16:9 | Small | 30×18 |
| 16:9 | Medium | 50×28 |
| 16:9 | Big | 100×56 |
| 16:9 | Super Large | 150×84 |
| 4:3 | Small | 30×24 |
| 4:3 | Medium | 50×38 |
| 4:3 | Big | 100×76 |
| 4:3 | Super Large | 150×114 |
| T-Shirt | Front / Back | 64x80 |
| T-Shirt | Left Sleeve / Right Sleeve | 64x48 |
| Tank Top | Front / Back | 64x64 |
| Mini Skirt | Front / Back | 128x64 |
| Shorts | Front / Back | 102x64 |
| Dress | Front | 102x154 |
| Dress | Back | 76x154 |
| Dress | Innerwear | 168x102 |

The complete game-derived preset list is stored in `src/heartopia_painter/resources/heartopia_draw_data.json`.

## Game-derived draw presets

The app reads Heartopia drawing sizes from the extracted table data:

- `DrawCanvas` for normal canvas presets
- `DrawCustom` for custom clothing/furniture presets
- `DrawSegment` for each drawable part size and source atlas position

Run this after a game update if you need to refresh the extracted sizes:

```powershell
.\.venv\Scripts\python.exe tools\extract_heartopia_draw_data.py
```

The main Painter app and Clothing Template Manager both use the same extracted JSON, so Tank Top, Dress, hats, shoes, furniture, and other draw items stay consistent.

### Dedicated Clothing Template Manager

Run `ClothingTemplateManager.cmd`, `DressTemplateManager.cmd`, or:

```powershell
.\.venv\Scripts\python.exe dress_template_manager.py
```

This opens a standalone template tool for all extracted Heartopia draw presets. It lets you choose type and part, import a separate source image for each part, then exports exact-size PNG templates. Drag the big preview to move the image, or use the mouse wheel over the preview to adjust scale. Use **Use current image for this type** when one source image should be reused across all parts of the selected draw type. By default it exports a full exact-size rectangle. Enable **Clip to mask / transparent shape** only when you imported a real mask/template for that part. Use those exported files in the main Painter app with the matching preset and part.
- If the game changes segment sizes later, rerun `tools\extract_heartopia_draw_data.py` instead of editing sizes by hand.

## Smart image prep

The **Smart image prep** panel runs before painting:

- **Smart** trims empty borders and fits the whole artwork into the grid.
- **Stretch** keeps the old behavior and forces the image into the grid.
- **Contain** preserves the whole image with background padding.
- **Cover** fills the whole grid and crops overflow.
- **Map preview to captured palette** converts the preview grid to the closest saved Heartopia shade before painting.
- **Dither palette-mapped image** can preserve more detail with limited palette colors.

## Quick start

1. Open Heartopia and make sure the palette + canvas you want to paint on are visible.
2. Start the app: `python main.py`
3. Choose a **Canvas preset**.
	- If you choose **T-Shirt**, **Tank Top**, or **Dress**, also choose a **Part**.
4. Click **Import image…** and pick an image.
5. Click **Select canvas area…** and drag a rectangle over the in-game canvas.
	- You’ll see a translucent preview to help align it.
	- Scroll the mouse wheel to enable/adjust a small zoom window near your cursor for precise alignment.
6. Set up your palette (one time per palette layout):
	- Click **Setup new color…** and follow the prompts.
		- If you want to use the bucket-fill speed boost, also capture:
			- **Set paint tool button**
			- **Set bucket tool button**
7. (Optional) Adjust timing values under **Timing / reliability**.
8. Click **Paint now**.

## Palette setup (how the wizard works)

When you click **Setup new color…**, the app will guide you through:

1. Capturing the **Shades panel** button (opens the shades UI) and the **Back** button (returns to main colors) if they haven’t been set yet.
2. Capturing the **main color** button for the color you’re adding.
3. Capturing all **shade** buttons for that color:
	- You open the shades panel in-game.
	- In the floating “Capture shades” window, click **Capture next shade**, then click the shade button location in the game.
	- Repeat until done, then click **Finish**.

Notes:

- The point-picking overlay samples the pixel RGB at the point you click.
- The overlay click is intercepted by the app (it does not press the in-game button).

## Tips for reliable painting

- If clicks don’t register in-game, increase:
  - **Mouse down hold** (e.g. 20–50 ms)
  - **After each click delay** (e.g. 60–120 ms)
- Keep the game window focused and don’t move the mouse during painting.
- On multi-monitor / DPI scaling setups, if overlays don’t line up, try moving the game to your primary display.

Speed tip:

- Enable **Stroke neighbors (rapid clicks)** to paint adjacent pixels with faster per-pixel clicking (often much faster on large solid areas).
- Enable **Bucket-fill most-used color first** to fill the entire canvas with the most common shade, then paint the remaining colors normally.
- Enable **Bucket-fill large regions (outline first)** (Paint-by-Color) to outline large same-shade regions and bucket-fill the inside.
	- This works best when **Bucket-fill most-used color first** is also enabled, because the canvas starts from a uniform base fill.

## Safety

- This app controls your mouse and clicks on your screen.
- A short countdown appears before painting starts so you can focus the game window.
- PyAutoGUI failsafe is enabled: move the mouse to the **top-left corner** to abort.
- You can also press **ESC** to pause while it’s painting (then use **Resume** in the app).

## Configuration (`config.json`)

The app writes settings to `config.json` in the repo folder, including:

- Palette button positions + sampled colors
- Your last selected preset
- Your last imported image path and selected canvas area
- Timing settings
- For **T-Shirt**, **Tank Top**, and **Dress**, each part stores its own last image + canvas rectangle

Resetting:

- To fully reset the app’s saved state, close the app and delete `config.json`.

## Troubleshooting

- **Wrong colors (e.g. yellows behave like blues):** use the **Fix colors: swap R/B** button (this edits your saved palette colors).
- **Overlay appears but you can’t click it:** press **ESC** to cancel and try again (make sure the app window isn’t minimized).
- **Painting starts on the wrong screen / wrong spot:** re-select the canvas area and verify the game hasn’t moved since selection.

## Notes / limitations

- Painting is currently a simple per-cell click approach.

# Drawing_Aqua
- Color matching is “closest configured shade” (RGB distance).
