/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Posit Software, PBC.
 *--------------------------------------------------------------------------------------------*/

import 'vs/css!./actionBarSeparator';
import * as React from 'react';

/**
 * ActionBarSeparator component.
 * @returns The component.
 */
export const ActionBarSeparator = () => {
	// Render.
	return (
		<div className='action-bar-separator'>
			<div className='action-bar-separator-icon codicon codicon-positron-separator' />
		</div>
	);
};
