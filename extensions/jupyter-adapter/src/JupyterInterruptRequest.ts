/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Posit, PBC.
 *--------------------------------------------------------------------------------------------*/

import { JupyterMessageSpec } from './JupyterMessageSpec';

/**
 * Represents a interrupt_request to the kernel
 *
 * @link https://jupyter-client.readthedocs.io/en/stable/messaging.html#kernel-interrupt
 */
export interface JupyterInterruptRequest extends JupyterMessageSpec {
}
