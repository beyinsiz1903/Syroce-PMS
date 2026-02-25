#!/usr/bin/env python3
"""
App Store Screenshot Generator for Syroce PMS
Generates screenshots for iPhone, iPad, and Apple Watch at required dimensions.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import zipfile
import glob

RAW_DIR = "/app/screenshots/raw"
OUTPUT_DIR = "/app/screenshots"
IPHONE_DIR = os.path.join(OUTPUT_DIR, "iphone")
IPAD_DIR = os.path.join(OUTPUT_DIR, "ipad")
WATCH_DIR = os.path.join(OUTPUT_DIR, "apple_watch")

# App Store required sizes
IPHONE_SIZES = {
    "6.5_portrait_1": (1242, 2688),
    "6.5_portrait_2": (1284, 2778),
    "6.5_landscape_1": (2688, 1242),
    "6.5_landscape_2": (2778, 1284),
}

IPAD_SIZES = {
    "12.9_portrait_1": (2048, 2732),
    "12.9_portrait_2": (2064, 2752),
    "12.9_landscape_1": (2732, 2048),
    "12.9_landscape_2": (2752, 2064),
}

WATCH_SIZES = {
    "ultra_3": (422, 514),
    "ultra": (410, 502),
    "series_11": (416, 496),
    "series_9": (396, 484),
    "series_6": (368, 448),
    "series_3": (312, 390),
}


def resize_to_fill(img, target_w, target_h):
    """Resize image to fill target dimensions, cropping center if needed."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # Source is wider - scale by height, crop width
        new_h = target_h
        new_w = int(src_ratio * target_h)
    else:
        # Source is taller - scale by width, crop height
        new_w = target_w
        new_h = int(target_w / src_ratio)

    img_resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img_cropped = img_resized.crop((left, top, left + target_w, top + target_h))
    return img_cropped


def create_watch_screenshot(img, target_w, target_h, screen_name):
    """Create Apple Watch-style screenshot from app screenshot."""
    # Create a dark background
    watch_img = Image.new("RGB", (target_w, target_h), (15, 15, 20))
    draw = ImageDraw.Draw(watch_img)

    # Scale down the original image to fit the watch screen
    # Add some padding
    padding = 8
    content_w = target_w - (padding * 2)
    content_h = target_h - (padding * 2) - 30  # Leave space for header

    # Resize and crop original image for the content area
    content_img = resize_to_fill(img, content_w, content_h)

    # Paste content
    watch_img.paste(content_img, (padding, padding + 25))

    # Add subtle rounded corner effect at top
    # Draw a small header bar
    draw.rectangle([(0, 0), (target_w, 24)], fill=(25, 25, 35))

    # Add time indicator
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
    except:
        font = ImageFont.load_default()
        small_font = font

    draw.text((target_w // 2 - 15, 5), "10:09", fill=(255, 255, 255), font=font)

    return watch_img


def process_screenshots():
    """Process all screenshots for each device category."""
    os.makedirs(IPHONE_DIR, exist_ok=True)
    os.makedirs(IPAD_DIR, exist_ok=True)
    os.makedirs(WATCH_DIR, exist_ok=True)

    # iPhone screenshots (portrait mode)
    iphone_files = sorted(glob.glob(os.path.join(RAW_DIR, "iphone_*.png")))
    print(f"Found {len(iphone_files)} iPhone raw screenshots")

    for img_path in iphone_files:
        basename = os.path.basename(img_path).replace("iphone_", "").replace(".png", "")
        img = Image.open(img_path).convert("RGB")
        print(f"  Processing iPhone: {basename} ({img.size})")

        for size_name, (w, h) in IPHONE_SIZES.items():
            output_path = os.path.join(IPHONE_DIR, f"{basename}_{size_name}.png")
            resized = resize_to_fill(img, w, h)
            resized.save(output_path, "PNG", optimize=True)
            print(f"    -> {size_name}: {w}x{h}")

    # iPad screenshots (portrait mode)
    ipad_files = sorted(glob.glob(os.path.join(RAW_DIR, "ipad_*.png")))
    print(f"\nFound {len(ipad_files)} iPad raw screenshots")

    for img_path in ipad_files:
        basename = os.path.basename(img_path).replace("ipad_", "").replace(".png", "")
        img = Image.open(img_path).convert("RGB")
        print(f"  Processing iPad: {basename} ({img.size})")

        for size_name, (w, h) in IPAD_SIZES.items():
            output_path = os.path.join(IPAD_DIR, f"{basename}_{size_name}.png")
            resized = resize_to_fill(img, w, h)
            resized.save(output_path, "PNG", optimize=True)
            print(f"    -> {size_name}: {w}x{h}")

    # Apple Watch screenshots
    # Use iPhone screenshots as source (they show compact UI better)
    watch_source_files = sorted(glob.glob(os.path.join(RAW_DIR, "iphone_*.png")))
    print(f"\nFound {len(watch_source_files)} source screenshots for Apple Watch")

    for img_path in watch_source_files:
        basename = os.path.basename(img_path).replace("iphone_", "").replace(".png", "")
        img = Image.open(img_path).convert("RGB")
        print(f"  Processing Watch: {basename} ({img.size})")

        for size_name, (w, h) in WATCH_SIZES.items():
            output_path = os.path.join(WATCH_DIR, f"{basename}_{size_name}.png")
            watch_img = create_watch_screenshot(img, w, h, basename)
            watch_img.save(output_path, "PNG", optimize=True)
            print(f"    -> {size_name}: {w}x{h}")


def create_zip():
    """Create a single ZIP file with all screenshots organized in folders."""
    zip_path = os.path.join(OUTPUT_DIR, "Syroce_PMS_AppStore_Screenshots.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # iPhone
        for f in sorted(glob.glob(os.path.join(IPHONE_DIR, "*.png"))):
            arcname = f"iPhone/{os.path.basename(f)}"
            zf.write(f, arcname)
            print(f"  ZIP: {arcname}")

        # iPad
        for f in sorted(glob.glob(os.path.join(IPAD_DIR, "*.png"))):
            arcname = f"iPad/{os.path.basename(f)}"
            zf.write(f, arcname)
            print(f"  ZIP: {arcname}")

        # Apple Watch
        for f in sorted(glob.glob(os.path.join(WATCH_DIR, "*.png"))):
            arcname = f"AppleWatch/{os.path.basename(f)}"
            zf.write(f, arcname)
            print(f"  ZIP: {arcname}")

    file_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"\nZIP created: {zip_path} ({file_size_mb:.1f} MB)")
    return zip_path


if __name__ == "__main__":
    print("=" * 60)
    print("Syroce PMS - App Store Screenshot Generator")
    print("=" * 60)
    process_screenshots()
    print("\n" + "=" * 60)
    print("Creating ZIP file...")
    print("=" * 60)
    zip_path = create_zip()
    print("\nDone!")
