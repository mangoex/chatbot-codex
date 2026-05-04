FROM node:22-alpine AS build
WORKDIR /app
ENV npm_config_fund=false
ENV npm_config_audit=false
COPY package*.json ./
RUN npm install
COPY tsconfig.json ./
COPY src ./src
COPY migrations ./migrations
RUN npm run build
RUN npm prune --omit=dev

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/migrations ./migrations
EXPOSE 3000
CMD ["node", "dist/src/server.js"]
