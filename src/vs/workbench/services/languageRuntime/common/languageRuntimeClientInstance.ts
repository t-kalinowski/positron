/*---------------------------------------------------------------------------------------------
 *  Copyright (C) 2023 Posit Software, PBC. All rights reserved.
 *--------------------------------------------------------------------------------------------*/

import { Event } from 'vs/base/common/event';
import { Disposable } from 'vs/base/common/lifecycle';

/**
 * The possible states for a language runtime client instance. These
 * represent the state of the communications channel between the client and
 * the runtime.
 */
export enum RuntimeClientState {
	/** The client has not yet been initialized */
	Uninitialized = 'uninitialized',

	/** The connection between the server and the client is being opened */
	Opening = 'opening',

	/** The connection between the server and the client has been established */
	Connected = 'connected',

	/** The connection between the server and the client is being closed */
	Closing = 'closing',

	/** The connection between the server and the client is closed */
	Closed = 'closed',
}

/**
 * The set of client types that can be generated by a language runtime. Note
 * that, because client types can share a namespace with other kinds of
 * widgets, each client type in Positron's API is prefixed with the string
 * "positron".
 */
export enum RuntimeClientType {
	Environment = 'positron.environment',
	Lsp = 'positron.lsp'

	// Future client types may include:
	// - Data viewer window
	// - Watch window/variable explorer
	// - Code inspector
	// - etc.
}

/**
 * An instance of a client widget generated by a language runtime. See
 * RuntimeClientType for the set of possible client types.
 *
 * This is a base interface that is extended by specific client types, and is
 * parameterized by the type of message that the client can send to the runtime.
 *
 * The client is responsible for disposing itself when it is no longer
 * needed; this will trigger the closure of the communications channel
 * between the client and the runtime.
 *
 * It can also be disposed by the runtime, in which case the client will
 * be notified via the onDidChangeClientState event.
 */
export interface IRuntimeClientInstance<T> extends Disposable {
	onDidChangeClientState: Event<RuntimeClientState>;
	onDidReceiveData: Event<T>;
	getClientState(): RuntimeClientState;
	getClientId(): string;
	getClientType(): RuntimeClientType;
	sendMessage(message: T): void;
}
