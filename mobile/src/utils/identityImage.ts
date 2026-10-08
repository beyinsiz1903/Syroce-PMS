import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

const OCR_MAX_WIDTH = 1600;
const OCR_JPEG_QUALITY = 0.72;

/**
 * Normalize a user-cropped identity photo before base64 encoding it.
 * Modern iPhones routinely produce 12–48 MP images; sending those unchanged
 * can exceed the API body limit and gives OCR far more background than text.
 */
export async function prepareIdentityPhoto(uri: string): Promise<string> {
  const context = ImageManipulator.manipulate(uri);
  context.resize({ width: OCR_MAX_WIDTH, height: null });
  const rendered = await context.renderAsync();
  const saved = await rendered.saveAsync({
    compress: OCR_JPEG_QUALITY,
    format: SaveFormat.JPEG,
  });
  return saved.uri;
}
