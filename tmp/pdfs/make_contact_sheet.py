from pathlib import Path
from PIL import Image, ImageDraw

p = Path("tmp/pdfs/rendered")
files = sorted(p.glob("page-*.png"))
images = []
width = 360
for file in files:
    image = Image.open(file).convert("RGB")
    image.thumbnail((width, 510))
    canvas = Image.new("RGB", (width, 535), "white")
    canvas.paste(image, ((width - image.width) // 2, 20))
    ImageDraw.Draw(canvas).text((8, 4), file.stem, fill="black")
    images.append(canvas)

sheet = Image.new("RGB", (width * 4, 535 * ((len(images) + 3) // 4)), "#cccccc")
for index, image in enumerate(images):
    sheet.paste(image, ((index % 4) * width, (index // 4) * 535))
sheet.save(p / "contact-sheet.png")
