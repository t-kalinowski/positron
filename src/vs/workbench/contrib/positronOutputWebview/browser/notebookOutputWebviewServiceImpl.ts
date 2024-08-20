/*---------------------------------------------------------------------------------------------
 *  Copyright (C) 2023-2024 Posit Software, PBC. All rights reserved.
 *  Licensed under the Elastic License 2.0. See LICENSE.txt for license information.
 *--------------------------------------------------------------------------------------------*/

import { VSBuffer } from 'vs/base/common/buffer';
import { Schemas } from 'vs/base/common/network';
import { URI } from 'vs/base/common/uri';
import { IWorkspaceTrustManagementService } from 'vs/platform/workspace/common/workspaceTrust';
import { IPositronRenderMessage, RendererMetadata, StaticPreloadMetadata } from 'vs/workbench/contrib/notebook/browser/view/renderers/webviewMessages';
import { preloadsScriptStr } from 'vs/workbench/contrib/notebook/browser/view/renderers/webviewPreloads';
import { INotebookRendererInfo, RendererMessagingSpec } from 'vs/workbench/contrib/notebook/common/notebookCommon';
import { INotebookService } from 'vs/workbench/contrib/notebook/common/notebookService';
import { NotebookOutputWebview } from 'vs/workbench/contrib/positronOutputWebview/browser/notebookOutputWebview';
import { INotebookOutputWebview, IPositronNotebookOutputWebviewService, WebviewType } from 'vs/workbench/contrib/positronOutputWebview/browser/notebookOutputWebviewService';
import { IOverlayWebview, IWebviewElement, IWebviewService, WebviewInitInfo } from 'vs/workbench/contrib/webview/browser/webview';
import { asWebviewUri } from 'vs/workbench/contrib/webview/common/webview';
import { IExtensionService } from 'vs/workbench/services/extensions/common/extensions';
import { ILanguageRuntimeMessageWebOutput } from 'vs/workbench/services/languageRuntime/common/languageRuntimeService';
import { ILanguageRuntimeSession } from 'vs/workbench/services/runtimeSession/common/runtimeSessionService';
import { dirname } from 'vs/base/common/resources';
import { INotebookRendererMessagingService } from 'vs/workbench/contrib/notebook/common/notebookRendererMessagingService';
import { ILogService } from 'vs/platform/log/common/log';
import { handleWebviewLinkClicksInjection } from './downloadUtils';
import { IInstantiationService } from 'vs/platform/instantiation/common/instantiation';

/**
 * Processed bundle of information about a message and how to render it for a webview.
 */
type MessageRenderInfo = {
	mimeType: string;
	renderer: INotebookRendererInfo;
	output: ILanguageRuntimeMessageWebOutput;
};

export class PositronNotebookOutputWebviewService implements IPositronNotebookOutputWebviewService {

	// Required for dependency injection
	readonly _serviceBrand: undefined;

	private _notebookWebviewByParentId = new Map<string, NotebookOutputWebview<IOverlayWebview>>();


	constructor(
		@IWebviewService private readonly _webviewService: IWebviewService,
		@INotebookService private readonly _notebookService: INotebookService,
		@IWorkspaceTrustManagementService private readonly _workspaceTrustManagementService: IWorkspaceTrustManagementService,
		@IExtensionService private readonly _extensionService: IExtensionService,
		@INotebookRendererMessagingService private readonly _notebookRendererMessagingService: INotebookRendererMessagingService,
		@ILogService private _logService: ILogService,
		@IInstantiationService private readonly _instantiationService: IInstantiationService
	) {
	}

	/**
	 * Gather the preferred renders and the mime type they are preferred for from a series of output
	 * messages.
	 * @param outputs An array of output messages to find renderers for.
	 * @returns An array of renderers and the mime type they are preferred for along with the
	 * associated output message.
	 */
	private _findRenderersForOutputs(outputs: ILanguageRuntimeMessageWebOutput[]): MessageRenderInfo[] {
		return outputs
			.map(output => {
				const info = this._findRendererForOutput(output);
				if (!info) {
					this._logService.warn(
						'Failed to find renderer for output with mime types: ' +
						Object.keys(output.data).join(', ') +
						'/nOutput will be ignored.'
					);
				}
				return info;
			})
			.filter((info): info is MessageRenderInfo => Boolean(info));
	}

	/**
	 * Gather preferred renderer and the mime type renderer is for from an output message.
	 *
	 * @param output An output messages to find renderers for.
	 * @returns A renderer and the mime type it is preferred for along with the output message.
	 */
	private _findRendererForOutput(output: ILanguageRuntimeMessageWebOutput): MessageRenderInfo | undefined {
		for (const mimeType in output.data) {
			const renderer = this._notebookService.getPreferredRenderer(mimeType);
			if (renderer) {
				return { mimeType, renderer, output };
			}
		}

		return undefined;
	}

	async createMultiMessageWebview({
		runtime,
		preReqMessages,
		displayMessage,
		viewType
	}: {
		runtime: ILanguageRuntimeSession;
		preReqMessages: ILanguageRuntimeMessageWebOutput[];
		displayMessage: ILanguageRuntimeMessageWebOutput;
		viewType?: string;
	}): Promise<INotebookOutputWebview | undefined> {

		const displayInfo = this._findRendererForOutput(displayMessage);
		if (!displayInfo) {
			this._logService.error(
				'Failed to find renderer for output message with mime types: ' +
				Object.keys(displayMessage.data).join(', ') +
				'.'
			);
			return undefined;
		}
		return this.createNotebookRenderOutput({
			id: displayMessage.id,
			runtime,
			displayMessageInfo: displayInfo,
			preReqMessagesInfo: this._findRenderersForOutputs(preReqMessages),
			viewType
		});
	}

	async createNotebookOutputWebview(
		runtime: ILanguageRuntimeSession,
		output: ILanguageRuntimeMessageWebOutput,
		viewType?: string,
	): Promise<INotebookOutputWebview | undefined> {
		// Check to see if any of the MIME types have a renderer associated with
		// them. If they do, prefer the renderer.
		for (const mimeType of Object.keys(output.data)) {
			// Don't use a renderer for non-widget MIME types
			if (mimeType === 'text/plain' ||
				mimeType === 'text/html' ||
				mimeType === 'image/png') {
				continue;
			}

			const renderer = this._notebookService.getPreferredRenderer(mimeType);
			if (renderer) {
				return this.createNotebookRenderOutput({
					id: output.id,
					runtime,
					displayMessageInfo: { mimeType, renderer, output },
					viewType
				});
			}
		}

		// If no dedicated renderer is found, check to see if there is a raw
		// HTML representation of the output.
		for (const mimeType of Object.keys(output.data)) {
			if (mimeType === 'text/html') {
				return this.createRawHtmlOutput({
					id: output.id,
					runtimeOrSessionId: runtime,
					html: output.data[mimeType],
					webviewType: WebviewType.Overlay
				});
			}
		}

		// No renderer found
		return Promise.resolve(undefined);
	}

	/**
	 * Gets renderer data for a given MIME type. This is used to inject only the
	 * needed renderers into the webview.
	 *
	 * @param mimeTypes The MIME types to get renderers for
	 * @returns An array of renderers that can render the given MIME type
	 */
	private getRendererData(mimeTypes: string[]): RendererMetadata[] {
		return this._notebookService.getRenderers()
			.filter(renderer => mimeTypes.some(mimeType => renderer.mimeTypes.includes(mimeType)))
			.map((renderer): RendererMetadata => {
				const entrypoint = {
					extends: renderer.entrypoint.extends,
					path: this.asWebviewUri(renderer.entrypoint.path, renderer.extensionLocation).toString()
				};
				return {
					id: renderer.id,
					entrypoint,
					mimeTypes: renderer.mimeTypes,
					messaging: renderer.messaging !== RendererMessagingSpec.Never,
					isBuiltin: renderer.isBuiltin
				};
			});
	}

	/**
	 * Convert a URI to a webview URI.
	 */
	private asWebviewUri(uri: URI, fromExtension: URI | undefined) {
		return asWebviewUri(uri, fromExtension?.scheme === Schemas.vscodeRemote ? { isRemote: true, authority: fromExtension.authority } : undefined);
	}

	/**
	 * Gets the static preloads for a given view type.
	 */
	private async getStaticPreloadsData(viewType: string | undefined):
		Promise<StaticPreloadMetadata[]> {
		if (!viewType) {
			return [];
		}
		const preloads = this._notebookService.getStaticPreloads(viewType);
		return Array.from(preloads, preload => {
			return {
				entrypoint: this.asWebviewUri(preload.entrypoint, preload.extensionLocation)
					.toString()
					.toString()
			};
		});
	}

	/**
	 * Gets the resource roots for a given messages and view type.
	 */
	private getResourceRoots(
		messages: ILanguageRuntimeMessageWebOutput[],
		viewType: string | undefined,
	): URI[] {

		const resourceRoots = new Array<URI>();

		for (const renderer of this._notebookService.getRenderers()) {
			// Add each renderer's parent folder
			resourceRoots.push(dirname(renderer.entrypoint.path));
		}

		if (viewType) {
			for (const preload of this._notebookService.getStaticPreloads(viewType)) {
				// Add each preload's parent folder
				resourceRoots.push(dirname(preload.entrypoint));

				// Add each preload's local resource roots
				resourceRoots.push(...preload.localResourceRoots);
			}
		}

		// Add auxiliary resource roots contained in the runtime message
		// These are currently used by positron-r's htmlwidgets renderer
		for (const message of messages) {
			if (message.resource_roots) {
				for (const root of message.resource_roots) {
					resourceRoots.push(URI.revive(root));
				}
			}
		}
		return resourceRoots;
	}

	private async createNotebookRenderOutput({
		id,
		runtime,
		displayMessageInfo,
		preReqMessagesInfo,
		viewType
	}: {
		id: string;
		runtime: ILanguageRuntimeSession;
		displayMessageInfo: MessageRenderInfo;
		preReqMessagesInfo?: MessageRenderInfo[];
		viewType?: string;
	}) {

		// Make message info into an array if it isn't already
		const messagesInfo = [...preReqMessagesInfo ?? [], displayMessageInfo];

		let webview: IOverlayWebview;

		const render = () => {
			// Loop through all the messages and render them in the webview
			for (const { output: message, mimeType, renderer } of messagesInfo) {
				const data = message.data[mimeType];
				// Send a message to the webview to render the output.
				const valueBytes = typeof (data) === 'string' ? VSBuffer.fromString(data) :
					VSBuffer.fromString(JSON.stringify(data));
				// TODO: We may need to pass valueBytes.buffer (or some version of it) as the `transfer`
				//   argument to postMessage.
				const transfer: ArrayBuffer[] = [];
				const webviewMessage: IPositronRenderMessage = {
					type: 'positronRender',
					outputId: message.id,
					elementId: 'container',
					rendererId: renderer.id,
					mimeType,
					metadata: message.metadata,
					valueBytes: valueBytes.buffer,
				};
				webview.postMessage(webviewMessage, transfer);
			}
		};

		const existingWebview = this._notebookWebviewByParentId.get(displayMessageInfo.output.parent_id);

		if (existingWebview) {
			// In the case we already have a webview for this parent id, we should skip creation and just send render message to existing webview.
			webview = existingWebview.webview;
			render();
			return;
		}
		// Create the preload script contents. This is a simplified version of the
		// preloads script that the notebook renderer API creates.
		const preloads = preloadsScriptStr({
			// PreloadStyles
			outputNodeLeftPadding: 0,
			outputNodePadding: 0,
			tokenizationCss: '',
		}, {
			// PreloadOptions
			dragAndDropEnabled: false
		}, {
			lineLimit: 1000,
			outputScrolling: true,
			outputWordWrap: false,
			linkifyFilePaths: false,
			minimalError: false,
		},
			this.getRendererData(messagesInfo.map(info => info.mimeType)),
			await this.getStaticPreloadsData(viewType),
			this._workspaceTrustManagementService.isWorkspaceTrusted(),
			id);

		// Create the metadata for the webview
		const webviewInitInfo: WebviewInitInfo = {
			contentOptions: {
				allowScripts: true,
				// Needed since we use the API ourselves, and it's also used by
				// preload scripts
				allowMultipleAPIAcquire: true,
				localResourceRoots: this.getResourceRoots(messagesInfo.map(info => info.output), viewType),
			},
			extension: {
				// Just choose last renderer for now. This may be insufficient in the future.
				id: displayMessageInfo.renderer.extensionId,
			},
			options: {},
			title: '',
		};

		// Create the webview itself
		webview = this._webviewService.createWebviewOverlay(webviewInitInfo);

		// Form the HTML to send to the webview. Currently, this is a very simplified version
		// of the HTML that the notebook renderer API creates, but it works for many renderers.
		webview.setHtml(`
			<head>
				<style nonce="${id}">
			#_defaultColorPalatte {
						color: var(--vscode-editor-findMatchHighlightBackground);
						background-color: var(--vscode-editor-findMatchBackground);
			}
			</style>
				${PositronNotebookOutputWebviewService.CssAddons}
			</head>
			<body>
			<div id='container'></div>
			<div id="_defaultColorPalatte"></div>
			<script type="module">${preloads}</script>
							</body>
								`);
		const scopedRendererMessaging = this._notebookRendererMessagingService.getScoped(id);

		const outputWebview = this._instantiationService.createInstance(
			NotebookOutputWebview<IOverlayWebview>,
			{
				id,
				sessionId: runtime.sessionId,
				webview,
				render,
				rendererMessaging: scopedRendererMessaging
			},
		);

		this._notebookWebviewByParentId.set(displayMessageInfo.output.parent_id, outputWebview);
		return outputWebview;
	}

	async createRawHtmlOutput<WType extends WebviewType>({ id, html, webviewType, runtimeOrSessionId }: {
		id: string;
		html: string;
		webviewType: WType;
		runtimeOrSessionId: ILanguageRuntimeSession | string;
	}): Promise<
		INotebookOutputWebview<WType extends WebviewType.Overlay ? IOverlayWebview : IWebviewElement>
	> {

		// Load the Jupyter extension. Many notebook HTML outputs have a dependency on jQuery,
		// which is provided by the Jupyter extension.
		const jupyterExtension = await this._extensionService.getExtension('ms-toolsai.jupyter');
		if (!jupyterExtension) {
			return Promise.reject(`Jupyter extension 'ms-toolsai.jupyter' not found`);
		}

		// Create the metadata for the webview
		const webviewInitInfo: WebviewInitInfo = {
			contentOptions: {
				allowScripts: true,
				localResourceRoots: [jupyterExtension.extensionLocation]
			},
			options: {},
			title: '',
			// Sometimes we don't have an active runtime (e.g. rendering html for a notebook pre
			// runtime start) so we can't get the extension id from the runtime.
			extension: typeof runtimeOrSessionId === 'string' ? undefined : { id: runtimeOrSessionId.runtimeMetadata.extensionId }
		};

		const webview = webviewType === WebviewType.Overlay
			? this._webviewService.createWebviewOverlay(webviewInitInfo)
			: this._webviewService.createWebviewElement(webviewInitInfo);

		// Form the path to the jQuery library and inject it into the HTML
		const jQueryPath = asWebviewUri(
			jupyterExtension.extensionLocation.with({
				path: jupyterExtension.extensionLocation.path +
					'/out/node_modules/jquery/dist/jquery.min.js'
			}));

		webview.setHtml(`
<script src='${jQueryPath}'></script>
${PositronNotebookOutputWebviewService.CssAddons}
${html}
<script>
const vscode = acquireVsCodeApi();
window.onload = function() {
	vscode.postMessage({
		__vscode_notebook_message: true,
		type: 'positronRenderComplete',
	});

	${handleWebviewLinkClicksInjection};
};
</script>`);

		return this._instantiationService.createInstance(
			NotebookOutputWebview,
			{
				id,
				sessionId: typeof runtimeOrSessionId === 'string' ? runtimeOrSessionId : runtimeOrSessionId.sessionId,
				webview,
			}
		) as NotebookOutputWebview<WType extends WebviewType.Overlay ? IOverlayWebview : IWebviewElement>;
	}

	/**
	 * A set of CSS addons to inject into the HTML of the webview. Used to do things like
	 * hide elements that are not functional in the context of positron such as links to
	 * pages that can't be opened.
	 */
	static readonly CssAddons = `
<style>
	/* Hide actions button that try and open external pages like opening source code as they don't currently work (See #2829)
	/* We do support download link clicks, so keep those. */
	.vega-actions a:not([download]) {
		display: none;
	}
</style>`;
}
