/*---------------------------------------------------------------------------------------------
 *  Copyright (C) 2024 Posit Software, PBC. All rights reserved.
 *--------------------------------------------------------------------------------------------*/


import { Application } from '../../../automation/out';
import { setTerminalTestSettings } from '../areas/terminal/terminal-helpers';


export class PositronConsoleFixtures {

	constructor(private app: Application) { }

	async updateTerminalSettings() {

		const additionalSettings: [string, string][] = [
			['editor.suggestOnTriggerCharacters', 'false'],
			['editor.autoClosingBrackets', '"never"'],
			['editor.autoIndent', '"none"'],
			['editor.quickSuggestions','{"other": "off", "comments": "off", "strings": "off"}']
		];

		await setTerminalTestSettings(this.app, additionalSettings);
	}

}