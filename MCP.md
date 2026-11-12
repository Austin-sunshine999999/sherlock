# Sherlock MCP server

This adapter exposes Sherlock's public username search as a Streamable HTTP MCP tool. It is the server component for a GPT/MCP connection; it still needs to be deployed to a container host with an HTTPS address before a GPT client can connect.

## Tool

- search_public_username checks one username against Sherlock's site list. By default it skips NSFW sites and checks the full remaining list. You can pass up to 50 exact site names to narrow the search.
- Results include claimed profile URLs and counts by Sherlock status. Sherlock can produce false positives, so verify links manually.
- The adapter does not save search results. The username is sent to the public sites Sherlock checks.

## Deploy with Docker

Run from the repository root:

~~~sh
docker build -f Dockerfile.mcp -t sherlock-mcp .
docker run --rm -p 8000:8000 -e MCP_BEARER_TOKEN="replace-with-a-long-random-secret" -e MCP_PUBLIC_BASE_URL="http://127.0.0.1:8000" -e MCP_ALLOWED_HOSTS="127.0.0.1:8000,localhost:8000" sherlock-mcp
~~~

For a hosted deployment, set the same environment variables in the hosting platform. Set MCP_PUBLIC_BASE_URL to the public HTTPS origin and MCP_ALLOWED_HOSTS to that hostname (for example, mcp.example.com,mcp.example.com:*). Keep MCP_BEARER_TOKEN in the host's secret manager; never commit it. The MCP endpoint is https://your-host/mcp.

## Connect a GPT/MCP client

Configure the client for Streamable HTTP at https://your-host/mcp and provide Authorization: Bearer <your token> using the client's secure secret settings. The included verifier accepts a static bearer token; a client that only supports an OAuth login flow will need an OAuth provider instead.

The server refuses to start without MCP_BEARER_TOKEN and checks the requested host against MCP_ALLOWED_HOSTS. Use searches only for authorized research. Sherlock queries public sites, not private account data.
