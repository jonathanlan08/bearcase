FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund --no-audit --legacy-peer-deps
COPY apps/web ./
RUN npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
