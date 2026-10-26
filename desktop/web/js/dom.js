/**
 * Lookup by id. Callers know the concrete element type from index.html, so the
 * result is typed as the union of the form/dialog APIs the pet actually uses.
 *
 * @param {string} id
 * @returns {HTMLElement & HTMLInputElement & HTMLButtonElement & HTMLDialogElement}
 */
export const $ = (id) => /** @type {any} */ (document.getElementById(id));
