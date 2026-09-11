/**
 * RSVP API Client Abstraction.
 * 
 * Communicates with the backend to retrieve chunked token plans.
 * Client sends raw text or textId and receives opaque tokens.
 */

export async function fetchPlanChunk({
  text = null,
  textId = null,
  chunkIndex = 0,
  chunkSize = 150,
  authToken = null,
  wpm = null,
}) {
  const headers = {
    'Content-Type': 'application/json',
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const payload = {
    chunk_index: chunkIndex,
    chunk_size: chunkSize,
  };
  if (wpm) {
    payload.wpm = wpm;
  }
  if (textId) {
    payload.text_id = textId;
  } else if (text) {
    payload.text = text;
  } else {
    return null;
  }

  const response = await fetch('/api/rsvp/plan', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Plan request failed with status ${response.status}`);
  }

  return await response.json();
}
