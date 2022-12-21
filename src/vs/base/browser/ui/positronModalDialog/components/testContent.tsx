/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Posit Software, PBC.
 *--------------------------------------------------------------------------------------------*/

import 'vs/css!./testContent';
import * as React from 'react';
import { useEffect, useState } from 'react'; // eslint-disable-line no-duplicate-imports

// TestContentProps interface.
interface TestContentProps {
	message: string;
}

// TestContent component.
export const TestContent = (props: TestContentProps) => {
	// Hooks.
	const [time, setTime] = useState<string>(new Date().toLocaleString());
	useEffect(() => {
		const interval = setInterval(() => {
			setTime(new Date().toLocaleString());
		}, 1000);
		return () => {
			clearInterval(interval);
		};
	}, []);

	// Render.
	return (
		<div className='test-content' >
			<div>
				Test Content
			</div>
			<div>
				Message: {props.message} Time: {time}
			</div>
		</div>
	);
};
