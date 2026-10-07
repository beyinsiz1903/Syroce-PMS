export type CameraResult = {
  canceled: boolean;
  assets?: Array<{ uri?: string }> | null;
};

export type CheckinCaptureResult<T> =
  | { status: 'cancelled' }
  | { status: 'parsed'; data: T }
  | { status: 'failed'; error: unknown };

type CaptureDependencies<T> = {
  launchCamera: () => Promise<CameraResult>;
  scanPhoto: (uri: string) => Promise<T>;
};

/**
 * Run the native camera and identity parser as one deterministic operation.
 * The screen calls this only after its live CameraView has been unmounted, so
 * iOS never has two camera sessions competing for the same device.
 */
export async function captureAndScanIdentity<T>({
  launchCamera,
  scanPhoto,
}: CaptureDependencies<T>): Promise<CheckinCaptureResult<T>> {
  try {
    const capture = await launchCamera();
    if (capture.canceled) return { status: 'cancelled' };

    const uri = capture.assets?.[0]?.uri;
    if (!uri) throw new Error('Kimlik fotoğrafı alınamadı. Lütfen yeniden deneyin.');

    return { status: 'parsed', data: await scanPhoto(uri) };
  } catch (error: unknown) {
    return { status: 'failed', error };
  }
}
