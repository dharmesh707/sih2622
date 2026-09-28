export type ApiErrorKind = "http" | "offline" | "timeout" | "malformed";

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    message: string,
    public readonly retryable: boolean,
    public readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const NOT_WRITTEN = "Your report is saved on this device and will be retried.";

// Worker-facing wording per status. Server details are only shown when they are short plain sentences;
// stack traces and validation dumps never reach the UI.
export function httpError(status: number, detail: unknown): ApiError {
  const plain = typeof detail === "string" && detail.length <= 160 ? detail : null;
  switch (status) {
    case 400:
      return new ApiError("http", "The server rejected the request. Check the report and try again.", false, status);
    case 401:
      return new ApiError("http", "Your connection token is invalid. Open Settings to update it.", false, status);
    case 403:
      return new ApiError("http", "This token is not allowed to do that. Ask your planner for access.", false, status);
    case 404:
      return new ApiError("http", plain ? `Not found on the server: ${plain}.` : "Not found on the server.", false, status);
    case 409:
      return new ApiError("http", plain ? `The server refused this report: ${plain}.` : "The server refused this report as a conflict.", false, status);
    case 413:
      return new ApiError("http", "This report is too large to send. Shorten it and try again.", false, status);
    case 415:
      return new ApiError("http", "The server did not accept the report format.", false, status);
    case 422:
      return new ApiError("http", plain ? `The server could not accept this report: ${plain}.` : "The server could not accept this report. Check the text and try again.", false, status);
    case 429:
      return new ApiError("http", `The server is busy. ${NOT_WRITTEN}`, true, status);
    case 503:
      return new ApiError("http", "ProgressSync is temporarily unavailable. Your report has not been written to the schedule.", true, status);
    case 502:
    case 504:
      return new ApiError("http", `The server could not be reached through the network gateway. ${NOT_WRITTEN}`, true, status);
    default:
      if (status >= 500) return new ApiError("http", `The server had a problem. ${NOT_WRITTEN}`, true, status);
      return new ApiError("http", `Unexpected server response (${status}).`, false, status);
  }
}

export const offlineError = () =>
  new ApiError("offline", "No connection. Your field update has been saved on this device and will sync later.", true);

export const timeoutError = () =>
  new ApiError("timeout", `The server did not answer in time. ${NOT_WRITTEN}`, true);

export const malformedError = () =>
  new ApiError("malformed", `The server sent an unexpected response. ${NOT_WRITTEN}`, true);

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : offlineError();
}
