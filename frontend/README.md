# RefundWeave Web

The standalone Angular 21 interface for RefundWeave. It consumes the FastAPI
`POST /api/v1/chat/stream` endpoint incrementally and keeps the returned LangGraph
thread ID in browser session storage.

## Local development

Start the API on port 8001, then:

```bash
npm install
npm start
```

Open <http://localhost:4200>. The Angular development proxy forwards `/api` to
FastAPI, matching the production Nginx routing.

## Checks

```bash
npm test
npm run build
```
