import { SseParser } from './chat-stream.service';

describe('SseParser', () => {
  it('parses events split across network chunks', () => {
    const parser = new SseParser();

    const first = parser.push(
      'id: 1\r\nevent: session\r\ndata: {"thread_id":"abc","sequence":1}\r\n\r\n' +
        'id: 2\nevent: workflow_',
    );
    const second = parser.push('step\ndata: {"node":"verify_order","label":"Verify order"}\n\n');

    expect(first).toEqual([
      {
        id: 1,
        event: 'session',
        data: { thread_id: 'abc', sequence: 1 },
      },
    ]);
    expect(second).toEqual([
      {
        id: 2,
        event: 'workflow_step',
        data: { node: 'verify_order', label: 'Verify order' },
      },
    ]);
  });

  it('flushes a final frame when the connection closes without a blank line', () => {
    const parser = new SseParser();
    parser.push('id: 3\nevent: done\ndata: {"sequence":3}');

    expect(parser.finish()).toEqual([{ id: 3, event: 'done', data: { sequence: 3 } }]);
  });

  it('ignores comments and unknown event types', () => {
    const parser = new SseParser();

    expect(parser.push(': heartbeat\n\nevent: private_state\ndata: {}\n\n')).toEqual([]);
  });
});
