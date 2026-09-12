export const OCR_LANGUAGES = [
  { code: 'eng', label: 'English' },
  { code: 'spa', label: 'Spanish' },
  { code: 'fra', label: 'French' },
  { code: 'deu', label: 'German' },
  { code: 'hin', label: 'Hindi' },
] as const;

const ingredientMarkers = [
  /\bingredients?\s*[:-]/i,
  /\bingredientes?\s*[:-]/i,
  /\bingr[ée]dients?\s*[:-]/i,
  /\binhaltsstoffe?\s*[:-]/i,
  /सामग्री\s*[:-]?/i,
];

const sectionEnd =
  /\n\s*(nutrition(?:al)? facts?|directions?|warnings?|caution|storage|manufactured|distributed|allergen information|informaci[oó]n nutricional|mode d'emploi|n[äa]hrwert|चेतावनी)\s*[:-]?/i;

/** Extract the likely ingredient block while preserving the original wording. */
export function extractIngredientSection(rawText: string): {
  text: string;
  sectionFound: boolean;
} {
  const normalized = rawText
    .replace(/\r/g, '\n')
    .replace(/[|•·]+/g, ', ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (!normalized) return { text: '', sectionFound: false };

  let start = -1;
  for (const marker of ingredientMarkers) {
    const match = marker.exec(normalized);
    if (match && (start < 0 || match.index < start))
      start = match.index + match[0].length;
  }
  if (start < 0) return { text: normalized, sectionFound: false };

  const candidate = normalized.slice(start).trim();
  const end = sectionEnd.exec(candidate);
  return {
    text: (end ? candidate.slice(0, end.index) : candidate).trim(),
    sectionFound: true,
  };
}

export function describeOcrQuality(
  confidence: number,
  sectionFound: boolean,
): string {
  if (confidence < 55)
    return 'Low-confidence scan. Check every ingredient or try a sharper, closer photo.';
  if (!sectionFound)
    return 'Text extracted, but no ingredient heading was detected. Remove unrelated label text before analyzing.';
  if (confidence < 75)
    return 'Ingredient section detected. Review spelling and punctuation before analyzing.';
  return 'Ingredient section detected. Review the extracted text before analyzing.';
}

/** Prepare an image locally for OCR with optional rotation and a conservative center crop. */
export async function prepareOcrImage(
  file: File,
  rotation: number,
  cropCenter: boolean,
): Promise<Blob> {
  if (typeof createImageBitmap !== 'function') return file;
  const bitmap = await createImageBitmap(file);
  const margin = cropCenter ? 0.08 : 0;
  const sourceX = bitmap.width * margin;
  const sourceY = bitmap.height * margin;
  const sourceWidth = bitmap.width * (1 - margin * 2);
  const sourceHeight = bitmap.height * (1 - margin * 2);
  const scale = Math.min(1, 2400 / Math.max(sourceWidth, sourceHeight));
  const drawWidth = Math.round(sourceWidth * scale);
  const drawHeight = Math.round(sourceHeight * scale);
  const quarterTurn = Math.abs(rotation) % 180 === 90;
  const canvas = document.createElement('canvas');
  canvas.width = quarterTurn ? drawHeight : drawWidth;
  canvas.height = quarterTurn ? drawWidth : drawHeight;
  const context = canvas.getContext('2d');
  if (!context) {
    bitmap.close();
    return file;
  }
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((rotation * Math.PI) / 180);
  context.drawImage(
    bitmap,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    -drawWidth / 2,
    -drawHeight / 2,
    drawWidth,
    drawHeight,
  );
  bitmap.close();
  return await new Promise<Blob>((resolve) =>
    canvas.toBlob((blob) => resolve(blob ?? file), 'image/png', 0.94),
  );
}
