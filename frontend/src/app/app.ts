import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ChatSseEvent, ChatStreamService, WorkflowStep } from './chat-stream.service';

interface ChatMessage {
  id: number;
  role: 'assistant' | 'user';
  text: string;
}

const WELCOME_MESSAGE: ChatMessage = {
  id: 0,
  role: 'assistant',
  text: 'Hi! I can help with a return or refund. Please share your full name or email and order number.',
};

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly chatService = inject(ChatStreamService);
  private messageSequence = 1;
  private activeRequest: AbortController | null = null;

  protected readonly draft = signal('');
  protected readonly messages = signal<ChatMessage[]>([WELCOME_MESSAGE]);
  protected readonly steps = signal<WorkflowStep[]>([]);
  protected readonly threadId = signal<string | null>(this.restoreThreadId());
  protected readonly isStreaming = signal(false);
  protected readonly awaitingConfirmation = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly statusLabel = computed(() => {
    if (this.isStreaming()) {
      return 'Working';
    }
    if (this.awaitingConfirmation()) {
      return 'Awaiting confirmation';
    }
    return 'Ready';
  });

  protected async send(message = this.draft()): Promise<void> {
    const normalized = message.trim();
    if (!normalized || this.isStreaming()) {
      return;
    }

    this.messages.update((items) => [
      ...items,
      { id: this.messageSequence++, role: 'user', text: normalized },
    ]);
    this.draft.set('');
    this.steps.set([]);
    this.errorMessage.set(null);
    this.isStreaming.set(true);
    this.activeRequest = new AbortController();

    try {
      await this.chatService.stream(
        {
          message: normalized,
          thread_id: this.threadId(),
        },
        (event) => this.handleEvent(event),
        this.activeRequest.signal,
      );
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        const messageText =
          error instanceof Error ? error.message : 'The support service is unavailable.';
        this.errorMessage.set(messageText);
      }
    } finally {
      this.activeRequest = null;
      this.isStreaming.set(false);
    }
  }

  protected startNewConversation(): void {
    if (this.isStreaming()) {
      return;
    }
    sessionStorage.removeItem('refundweave.threadId');
    this.threadId.set(null);
    this.messages.set([WELCOME_MESSAGE]);
    this.steps.set([]);
    this.awaitingConfirmation.set(false);
    this.errorMessage.set(null);
    this.draft.set('');
  }

  protected usePrompt(prompt: string): void {
    void this.send(prompt);
  }

  protected displayText(text: string): string {
    return text.replaceAll('**', '');
  }

  private handleEvent(event: ChatSseEvent): void {
    if (event.event === 'session') {
      const threadId = this.stringValue(event.data, 'thread_id');
      if (threadId) {
        this.threadId.set(threadId);
        sessionStorage.setItem('refundweave.threadId', threadId);
      }
      return;
    }

    if (event.event === 'workflow_step') {
      const node = this.stringValue(event.data, 'node');
      if (!node) {
        return;
      }
      const step: WorkflowStep = {
        node,
        label: this.stringValue(event.data, 'label') ?? 'Process request',
        stage: this.stringValue(event.data, 'stage') ?? 'working',
        detail: this.stringValue(event.data, 'detail') ?? 'Step completed.',
      };
      this.steps.update((items) => [...items.filter((item) => item.node !== node), step]);
      return;
    }

    if (event.event === 'message') {
      const response = this.stringValue(event.data, 'message');
      if (response) {
        this.messages.update((items) => [
          ...items,
          { id: this.messageSequence++, role: 'assistant', text: response },
        ]);
      }
      this.awaitingConfirmation.set(event.data['awaiting_confirmation'] === true);
      return;
    }

    if (event.event === 'error') {
      this.errorMessage.set(
        this.stringValue(event.data, 'message') ?? 'The chat request could not be completed.',
      );
    }
  }

  private stringValue(data: Record<string, unknown>, key: string): string | null {
    const value = data[key];
    return typeof value === 'string' ? value : null;
  }

  private restoreThreadId(): string | null {
    return sessionStorage.getItem('refundweave.threadId');
  }
}
