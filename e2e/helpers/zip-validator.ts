import AdmZip from 'adm-zip';
import * as path from 'path';

export interface ZipValidationResult {
  valid: boolean;
  fileCount: number;
  jpgCount: number;
  hasManifest: boolean;
  filenames: string[];
  errors: string[];
  sizeBytes: number;
}

const ZIP_MAGIC_BYTES = Buffer.from([0x50, 0x4b, 0x03, 0x04]);

export function validateZipBuffer(buffer: Buffer): ZipValidationResult {
  const result: ZipValidationResult = {
    valid: false,
    fileCount: 0,
    jpgCount: 0,
    hasManifest: false,
    filenames: [],
    errors: [],
    sizeBytes: buffer.length,
  };

  if (buffer.length < 4) {
    result.errors.push(`Buffer too small: ${buffer.length} bytes`);
    return result;
  }

  if (!buffer.subarray(0, 4).equals(ZIP_MAGIC_BYTES)) {
    result.errors.push(
      `Invalid ZIP magic bytes: got ${buffer.subarray(0, 4).toString('hex')}, expected ${ZIP_MAGIC_BYTES.toString('hex')}`
    );
    return result;
  }

  try {
    const zip = new AdmZip(buffer);
    const entries = zip.getEntries();

    result.fileCount = entries.length;
    result.filenames = entries.map((e) => e.entryName);

    for (const entry of entries) {
      const ext = path.extname(entry.entryName).toLowerCase();
      if (ext === '.jpg' || ext === '.jpeg') {
        result.jpgCount++;
      }
      if (entry.entryName.toLowerCase() === 'manifest.csv') {
        result.hasManifest = true;
      }
    }

    if (result.jpgCount === 0) {
      result.errors.push('ZIP contains no JPEG files');
    }
    if (!result.hasManifest) {
      result.errors.push('ZIP is missing manifest.csv');
    }

    result.valid = result.jpgCount > 0 && result.hasManifest && result.errors.length === 0;
  } catch (err) {
    result.errors.push(`ZIP parse error: ${err instanceof Error ? err.message : String(err)}`);
  }

  return result;
}
