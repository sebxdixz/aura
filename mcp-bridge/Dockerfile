FROM node:20-alpine

WORKDIR /usr/src/app

COPY package*.json ./
RUN npm install --omit=dev

# mcp-atlassian is a Python package. We install both `mcp-atlassian`
# and `uv/uvx` so command strategy can be switched via env vars.
RUN apk add --no-cache python3 py3-pip && pip3 install --no-cache-dir --break-system-packages uv mcp-atlassian

COPY server.js .

EXPOSE 8080

CMD ["node", "server.js"]
