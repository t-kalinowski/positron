/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Posit Software, PBC.
 *--------------------------------------------------------------------------------------------*/

import { Disposable } from 'vs/base/common/lifecycle';
import { IInstantiationService } from 'vs/platform/instantiation/common/instantiation';
import { ReplError } from 'vs/workbench/contrib/repl/browser/replError';
import { LinkDetector } from 'vs/workbench/contrib/debug/browser/linkDetector';
import { handleANSIOutput } from 'vs/workbench/contrib/debug/browser/debugANSIHandling';
import { IThemeService } from 'vs/platform/theme/common/themeService';
import { BareFontInfo } from 'vs/editor/common/config/fontInfo';
import { applyFontInfo } from 'vs/editor/browser/config/domFontInfo';
import { Emitter, Event } from 'vs/base/common/event';

/**
 * Represents the output generated by a single code execution in a REPL cell.
 */
export class ReplOutput extends Disposable {
	private readonly _container: HTMLElement;

	readonly onDidChangeHeight: Event<void>;
	private readonly _onDidChangeHeight;

	constructor(
		private readonly _parentElement: HTMLElement,
		private readonly _monoFont: BareFontInfo,
		@IInstantiationService private readonly _instantiationService: IInstantiationService,
		@IThemeService private readonly _themeService: IThemeService) {
		super();

		// Create our root output container
		this._container = document.createElement('div');
		this._container.classList.add('repl-output');
		this._parentElement.appendChild(this._container);

		// Make the container focusable
		this._container.tabIndex = 0;

		this._onDidChangeHeight = this._register(new Emitter<void>());
		this.onDidChangeHeight = this._onDidChangeHeight.event;
	}

	/**
	 * Emits preformatted text to the output area.
	 *
	 * @param output The output to emit
	 */
	emitOutput(output: string, error: boolean | undefined) {
		const pre = document.createElement('pre');

		// Apply error color to errors.
		if (error) {
			pre.classList.add('repl-error');
		}

		// Import fixed-width font info
		applyFontInfo(pre, this._monoFont);

		pre.appendChild(handleANSIOutput(output,
			this._instantiationService.createInstance(LinkDetector),
			this._themeService,
			undefined));
		this._container.appendChild(pre);
	}

	/**
	 * Emits preformatted input to the output area.
	 *
	 * @param input The input to emit
	 */
	emitInput(input: string) {
		const pre = document.createElement('pre');
		pre.innerText = `>  ${input}`;
		pre.classList.add('repl-input');
		this._container.appendChild(pre);
	}

	/**
	 * Emits an error to the output stream.
	 *
	 * @param error The error to emit; expected to be an Error JSON object, but
	 * if not will be treated as text
	 */
	emitError(error: string) {
		const err: ReplError =
			this._instantiationService.createInstance(ReplError,
				error,
				this._monoFont);
		this._register(err);

		// The error can change height when the traceback region is expanded or
		// collapsed.
		this._register(err.onDidChangeHeight(() => {
			this._onDidChangeHeight.fire();
		}));
		err.render(this._container);
	}

	/**
	 * Emit raw HTML to the output stream.
	 *
	 * @param html The raw HTML to emit
	 */
	emitHtml(html: string) {
		const container = document.createElement('div');
		container.innerHTML = html;
		this._container.appendChild(container);
	}

	/**
	 * Get the DOM element containing the outputs
	 *
	 * @returns The containing DOM element
	 */
	getDomNode(): HTMLElement {
		return this._container;
	}
}
