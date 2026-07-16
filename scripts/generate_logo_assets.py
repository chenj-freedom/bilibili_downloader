from pathlib import Path

from PIL import Image, ImageDraw


PINK = "#FB7299"
CYAN = "#00C4D9"
DARK = "#20242C"
CANVAS_SIZE = 512
RENDER_SCALE = 4


def build_svg() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-labelledby="title desc">
  <title id="title">Bilibili Downloader logo</title>
  <desc id="desc">A pink retro television with a download arrow and play symbol</desc>
  <defs>
    <mask id="screen-cutout" maskUnits="userSpaceOnUse">
      <rect width="512" height="512" fill="white"/>
      <rect x="126" y="198" width="260" height="142" rx="48" fill="black"/>
    </mask>
    <mask id="play-cutout" maskUnits="userSpaceOnUse">
      <rect width="512" height="512" fill="white"/>
      <path d="M244 242v36l31-18z" fill="black"/>
    </mask>
  </defs>

  <g fill="none" stroke="{CYAN}" stroke-width="16" stroke-linecap="round">
    <path d="M84 144 48 122"/>
    <path d="M76 177H36"/>
    <path d="m428 144 36-22"/>
    <path d="M436 177h40"/>
  </g>

  <g fill="none" stroke="{PINK}" stroke-width="34" stroke-linecap="round">
    <path d="m194 158-52-76"/>
    <path d="m318 158 52-76"/>
  </g>

  <rect x="116" y="392" width="42" height="58" rx="18" fill="{PINK}"/>
  <rect x="354" y="392" width="42" height="58" rx="18" fill="{PINK}"/>
  <rect x="80" y="145" width="352" height="273" rx="78" fill="{PINK}" mask="url(#screen-cutout)"/>

  <path d="M226 218a12 12 0 0 1 12-12h36a12 12 0 0 1 12 12v62h30a10 10 0 0 1 7 17l-60 60a10 10 0 0 1-14 0l-60-60a10 10 0 0 1 7-17h30z" fill="{PINK}" mask="url(#play-cutout)"/>

  <circle cx="142" cy="378" r="16" fill="{DARK}"/>
  <circle cx="190" cy="378" r="16" fill="{DARK}"/>
  <g fill="{DARK}">
    <rect x="330" y="354" width="14" height="48" rx="7"/>
    <rect x="356" y="354" width="14" height="48" rx="7"/>
    <rect x="382" y="354" width="14" height="48" rx="7"/>
  </g>
</svg>
'''


def draw_logo(size: int) -> Image.Image:
    scale = size / CANVAS_SIZE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def point(x: int, y: int) -> tuple[int, int]:
        return round(x * scale), round(y * scale)

    def box(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
        return round(left * scale), round(top * scale), round(right * scale), round(bottom * scale)

    def rounded_line(start: tuple[int, int], end: tuple[int, int], width: int, fill: str) -> None:
        scaled_start = point(*start)
        scaled_end = point(*end)
        scaled_width = round(width * scale)
        radius = scaled_width // 2
        draw.line((scaled_start, scaled_end), fill=fill, width=scaled_width)
        for x, y in (scaled_start, scaled_end):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)

    rounded_line((84, 144), (48, 122), 16, CYAN)
    rounded_line((76, 177), (36, 177), 16, CYAN)
    rounded_line((428, 144), (464, 122), 16, CYAN)
    rounded_line((436, 177), (476, 177), 16, CYAN)

    rounded_line((194, 158), (142, 82), 34, PINK)
    rounded_line((318, 158), (370, 82), 34, PINK)

    draw.rounded_rectangle(box(116, 392, 158, 450), radius=round(18 * scale), fill=PINK)
    draw.rounded_rectangle(box(354, 392, 396, 450), radius=round(18 * scale), fill=PINK)
    draw.rounded_rectangle(box(80, 145, 432, 418), radius=round(78 * scale), fill=PINK)
    draw.rounded_rectangle(box(126, 198, 386, 340), radius=round(48 * scale), fill=(0, 0, 0, 0))

    draw.rounded_rectangle(box(226, 206, 286, 296), radius=round(12 * scale), fill=PINK)
    draw.polygon([point(189, 280), point(323, 280), point(256, 364)], fill=PINK)
    draw.polygon([point(244, 242), point(244, 278), point(275, 260)], fill=(0, 0, 0, 0))

    draw.ellipse(box(126, 362, 158, 394), fill=DARK)
    draw.ellipse(box(174, 362, 206, 394), fill=DARK)
    for left in (330, 356, 382):
        draw.rounded_rectangle(box(left, 354, left + 14, 402), radius=round(7 * scale), fill=DARK)

    return image


def generate_assets(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logo.svg").write_text(build_svg(), encoding="utf-8")

    image = draw_logo(CANVAS_SIZE * RENDER_SCALE).resize(
        (CANVAS_SIZE, CANVAS_SIZE),
        Image.Resampling.LANCZOS,
    )
    optimized_logo = image.quantize(
        colors=128,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.NONE,
    )
    optimized_logo.save(output_dir / "logo.png", format="PNG", optimize=True)
    image.save(
        output_dir / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
    )


if __name__ == "__main__":
    generate_assets(Path(__file__).resolve().parents[1] / "web")
