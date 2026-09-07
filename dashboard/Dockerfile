FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# This project doesn't have a public/ directory yet. Next's own build
# doesn't require one, but ensuring it exists here means the final stage's
# COPY below never has to guess whether the source will have it -- it can
# always add one later (favicon, static assets) with zero Dockerfile changes.
RUN mkdir -p public
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/next.config.js ./next.config.js
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start"]
