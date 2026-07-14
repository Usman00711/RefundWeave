import { TestBed } from '@angular/core/testing';

import { App } from './app';
import { ChatSseEvent, ChatStreamService } from './chat-stream.service';

class MockChatStreamService {
  async stream(_request: unknown, onEvent: (event: ChatSseEvent) => void): Promise<void> {
    onEvent({
      id: 1,
      event: 'session',
      data: { thread_id: '8e8a03a8-b2f6-4d31-89e1-58d849a06d44' },
    });
    onEvent({
      id: 2,
      event: 'workflow_step',
      data: {
        node: 'identify_customer',
        label: 'Identify customer',
        stage: 'identifying_customer',
        detail: 'Looked up the customer record.',
      },
    });
    onEvent({
      id: 3,
      event: 'message',
      data: {
        message: 'No change has been made yet. Reply **confirm refund** to proceed.',
        stage: 'awaiting_confirmation',
        awaiting_confirmation: true,
      },
    });
    onEvent({ id: 4, event: 'done', data: {} });
  }
}

describe('App', () => {
  beforeEach(async () => {
    sessionStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ChatStreamService, useClass: MockChatStreamService }],
    }).compileComponents();
  });

  it('renders the RefundWeave support experience', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('RefundWeave');
    expect(fixture.nativeElement.textContent).toContain('How can we help?');
    expect(fixture.nativeElement.textContent).toContain('Nothing to review yet');
  });

  it('renders streamed progress and the explicit confirmation action', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const buttons = Array.from(
      element.querySelectorAll<HTMLButtonElement>('.starter-prompts button'),
    );
    buttons[0]?.click();

    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Identify customer');
    expect(fixture.nativeElement.textContent).toContain('Confirm refund');
    expect(sessionStorage.getItem('refundweave.threadId')).toBe(
      '8e8a03a8-b2f6-4d31-89e1-58d849a06d44',
    );
  });
});
