/** The expanding hero's frame at `progress` (0 = small card, 1 = the whole screen). */
export function heroFrame(progress: number, screenWidth: number, screenHeight: number) {
  'worklet';
  const p = Math.min(Math.max(progress, 0), 1);
  // Start as a portrait card that still fits on a small phone.
  const startWidth = Math.min(300, screenWidth * 0.72);
  const startHeight = Math.min(400, screenHeight * 0.5);
  return {
    width: startWidth + (screenWidth - startWidth) * p,
    height: startHeight + (screenHeight - startHeight) * p,
    radius: 24 * (1 - p),
    // The two title lines slide apart until they are off screen.
    textShift: p * screenWidth * 0.75,
  };
}
