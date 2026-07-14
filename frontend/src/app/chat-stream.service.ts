import { Injectable } from '@angular/core';

export type ChatEventName = 'session' | 'workflow_step' | 'message' | 'done' | 'error';

export interface ChatSseEvent {
  id: number;
  event: ChatEventName;
  data: Record<string, unknown>;
}

export interface ChatStreamRequest {
  message: string;
  thread_id: string | null;
}

export interface WorkflowStep {
  node: string;
  label: string;
  stage: string;
  detail: string;
}

export class SseParser {
  private buffer = '';

  push(chunk: string): ChatSseEvent[] {
    this.buffer += chunk.replaceAll('\r\n', '\n');
    const frames = this.buffer.split('\n\n');
    this.buffer = frames.pop() ?? '';
    return frames.flatMap((frame) => this.parseFrame(frame));
  }

  finish(): ChatSseEvent[] {
    const finalFrame = this.buffer.trim();
    this.buffer = '';
    return finalFrame ? this.parseFrame(finalFrame) : [];
  }

  private parseFrame(frame: string): ChatSseEvent[] {
    let id = 0;
    let eventName = '';
    const dataLines: string[] = [];

    for (const line of frame.split('\n')) {
      if (!line || line.startsWith(':')) {
        continue;
      }
      const separator = line.indexOf(':');
      const field = separator === -1 ? line : line.slice(0, separator);
      const value = separator === -1 ? '' : line.slice(separator + 1).trimStart();
      if (field === 'id') {
        id = Number(value);
      } else if (field === 'event') {
        eventName = value;
      } else if (field === 'data') {
        dataLines.push(value);
      }
    }

    if (!this.isEventName(eventName) || dataLines.length === 0) {
      return [];
    }
    const parsed: unknown = JSON.parse(dataLines.join('\n'));
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('The server returned an invalid stream event.');
    }
    return [{ id, event: eventName, data: parsed as Record<string, unknown> }];
  }

  private isEventName(value: string): value is ChatEventName {
    return ['session', 'workflow_step', 'message', 'done', 'error'].includes(value);
  }
}

@Injectable({ providedIn: 'root' })
export class ChatStreamService {
  async stream(
    request: ChatStreamRequest,
    onEvent: (event: ChatSseEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      cache: 'no-store',
      signal,
    });

    if (!response.ok) {
      throw new Error(await this.errorMessage(response));
    }
    if (!response.body) {
      throw new Error('Streaming is not supported by this browser.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const parser = new SseParser();

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        onEvent(event);
      }
    }
    for (const event of parser.push(decoder.decode())) {
      onEvent(event);
    }
    for (const event of parser.finish()) {
      onEvent(event);
    }
  }

  private async errorMessage(response: Response): Promise<string> {
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'error' in body) {
        const error = (body as { error?: unknown }).error;
        if (error && typeof error === 'object' && 'message' in error) {
          const message = (error as { message?: unknown }).message;
          if (typeof message === 'string') {
            return message;
          }
        }
      }
    } catch {
      // Use the stable fallback below when an upstream returns non-JSON content.
    }
    return `The support service returned HTTP ${response.status}.`;
  }
}
