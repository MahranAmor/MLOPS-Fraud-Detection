# ====================================================================
# Stage 1: Dependencies - Installation des dépendances
# ====================================================================
FROM node:18-alpine AS deps

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY frontend/package.json frontend/package-lock.json* ./

# Installer les dépendances
RUN npm ci 

# ====================================================================
# Stage 2: Builder - Build de l'application Next.js
# ====================================================================
FROM node:18-alpine AS builder

WORKDIR /app

# Copier les node_modules depuis deps
COPY --from=deps /app/node_modules ./node_modules

# Copier tout le code source du frontend
COPY frontend/ .

# Variables d'environnement pour le build
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build de l'application Next.js
RUN npm run build

# ====================================================================
# Stage 3: Runner - Image finale légère
# ====================================================================
FROM node:18-alpine AS runner

# Metadata labels
LABEL maintainer="Bassem Ben Hamed"
LABEL description="Frontend Next.js pour la détection de fraude"
LABEL version="1.0.0"

WORKDIR /app

# Créer un utilisateur non-root
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copier les fichiers nécessaires depuis builder
#COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Définir les permissions
#RUN chown -R nextjs:nodejs /app

# Variables d'environnement
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Exposer le port
EXPOSE 3000

# Passer à l'utilisateur non-root
USER nextjs

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

# Commande pour lancer l'application
CMD ["node", "server.js"]