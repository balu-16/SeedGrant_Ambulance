/**
 * Typed transport error shared by the api client and the portal-auth service
 * (kept in its own module so both can import it without an import cycle).
 */

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status = 0, code = "UNKNOWN") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}
