import { headers } from "next/headers";

/**
 * Request header set by the middleware when a request arrived on a workspace's
 * own domain rather than on the platform host.
 */
export const CUSTOM_DOMAIN_HEADER = "x-custom-domain";

/**
 * Prefix for links between public knowledge-base pages.
 *
 * The same pages serve two URL shapes:
 *
 *   platform host     /kb/acme            /kb/acme/how-to-request-a-refund
 *   custom domain     /                   /how-to-request-a-refund
 *
 * On a custom domain the host already identifies the workspace, so the
 * `/kb/<slug>` prefix does not exist there — emitting it produces a 404.
 * Server components call this to build links that are correct on both.
 */
export function kbBasePath(slug: string): string {
  return headers().get(CUSTOM_DOMAIN_HEADER) ? "" : `/kb/${slug}`;
}
