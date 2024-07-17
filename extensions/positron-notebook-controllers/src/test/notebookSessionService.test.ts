/*---------------------------------------------------------------------------------------------
 *  Copyright (C) 2024 Posit Software, PBC. All rights reserved.
 *  Licensed under the Elastic License 2.0. See LICENSE.txt for license information.
 *--------------------------------------------------------------------------------------------*/

import * as assert from 'assert';
import * as positron from 'positron';
import * as sinon from 'sinon';
import * as vscode from 'vscode';
import { NotebookSessionService } from '../notebookSessionService';

suite('NotebookSessionService', () => {
	let notebookSessionService: NotebookSessionService;
	let sandbox: sinon.SinonSandbox;

	setup(() => {
		sandbox = sinon.createSandbox();
		notebookSessionService = new NotebookSessionService();
	});

	teardown(() => {
		sandbox.restore();
	});

	test('Shutdown non-existent runtime -> Start new runtime', async () => {
		// Shutdown, when no runtime session is running for the notebook.

		const notebookUri = vscode.Uri.file('notebook.ipynb');
		const runtimeId = 'runtimeId';

		await notebookSessionService.shutdownRuntimeSession(notebookUri);

		assert.strictEqual(notebookSessionService.getNotebookSession(notebookUri), undefined);

		// Start a new runtime session.

		const session = {
			metadata: {
				sessionId: 'test-session',
			},
			runtimeMetadata: {
				languageName: 'languageName',
				runtimeName: 'runtimeName',
				runtimeVersion: 'runtimeVersion',
			},
		} as positron.LanguageRuntimeSession;
		const startSessionStub = sandbox.stub(positron.runtime, 'startLanguageRuntime').resolves(session);

		await notebookSessionService.startRuntimeSession(notebookUri, runtimeId);

		assert(startSessionStub.calledOnce);
		assert.strictEqual(notebookSessionService.getNotebookSession(notebookUri), session);
	});
});
