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
    // Surface server-provided Persian detail (e.g. quota/rate-limit messages)
    // and standard headers to callers for UI handling.
    let detail = null;
    try {
      const data = await response.json();
      detail = (data && data.detail) || null;
    } catch (e) {
      /* non-JSON body: keep null detail */
    }
    const err = new Error(`Plan request failed with status ${response.status}`);
    err.status = response.status;
    err.detail = detail;
    err.retryAfter = response.headers.get('retry-after');
    throw err;
  }

  return await response.json();
}
