# 🚀 Guía de Configuración - Portfolio de Sebastian Diaz

## Paso 1: Verificar Instalación ✅

Las dependencias principales ya están instaladas:
- ✅ Expo 51
- ✅ React 18
- ✅ React Native Reanimated 4.1
- ✅ React Native Gesture Handler 2.28
- ✅ Expo AV (Video support)

## Paso 2: Verificar la Estructura

```bash
cd portfolio
```

Estructura del proyecto:
```
app/                    → Rutas principales (Expo Router)
  _layout.tsx          → Configuración de GestureHandler
  index.tsx            → Página principal
  
src/components/        → Componentes React
  StackCarousel.tsx    → Carrusel cinético (hero)
  ProjectCard.tsx      → Tarjeta de proyecto con video
  ProjectsGrid.tsx     → Grilla de proyectos (hover=invert)
  LabSection.tsx       → GitHub feed con animación cascada
  
src/constants/
  projects.ts          → Datos de proyectos
  
babel.config.js        → Configuración de Reanimated
app.json              → Configuración de Expo
vercel.json           → Configuración de Vercel
```

## Paso 3: Agregar tus Proyectos

Edita `src/constants/projects.ts`:

```typescript
export const PROJECTS: Project[] = [
  {
    id: 'proyecto-1',
    name: 'Mi Proyecto',
    description: 'Descripción breve',
    videoUrl: 'https://tu-cdn.com/video.mp4', // ← Importante!
    techs: ['React', 'TypeScript'],
    links: {
      github: 'https://github.com/tu-usuario/repo',
      website: 'https://tu-sitio.com',
      demo: 'https://demo.tu-sitio.com'
    }
  },
  // ... más proyectos
];
```

## Paso 4: Preparar Videos

Para optimizar videos (crítico para 60 FPS):

```bash
# Convertir a MP4 con bajo bitrate
ffmpeg -i input.mov \
  -c:v libx264 \
  -crf 28 \
  -preset fast \
  -b:v 2M \
  -b:a 128k \
  output.mp4
```

**Subir a:** Cloudinary, Vercel Blob Storage, o tu CDN preferido

## Paso 5: Desarrollo Local

```bash
# Iniciar servidor web
npm run dev

# La app abrirá en http://localhost:8081
```

**En el navegador:**
- Prueba el swipe del carrusel (arrastra izquierda/derecha)
- Haz hover en los proyectos de la grilla
- Scroll para ver la sección "The Lab"

## Paso 6: Personalizar Diseño (Monocromático)

**Opción A: Fondo Blanco (default)**
- Texto: Negro (#000000)
- Bordes: Negro
- Fondo: Blanco (#FFFFFF)

**Opción B: Fondo Negro**

En `app/index.tsx`, cambiar:
```typescript
backgroundColor: '#FFFFFF' → '#000000'
```

En estilos de componentes:
```typescript
color: '#000000' → '#FFFFFF'
backgroundColor: '#FFFFFF' → '#000000'
```

## Paso 7: Desplegar en Vercel

### Opción A: Vercel Dashboard (Recomendado)

1. Ir a https://vercel.com/new
2. Conectar GitHub
3. Seleccionar tu repositorio `sebastiandiaz.eeden.app`
4. Vercel detectará automáticamente que es Expo
5. Click en "Deploy"

### Opción B: Vercel CLI

```bash
# Instalar Vercel CLI
npm i -g vercel

# Deploy
vercel

# Vercel te guiará interactivamente
```

## Paso 8: Configurar GitHub Feed

La sección "The Lab" obtiene repositorios de GitHub automáticamente.

**Límite sin token:** 60 requests/hora (suficiente para desarrollo)

**Para producción, agregar token:**

1. Crear token en GitHub:
   - Ir a https://github.com/settings/tokens
   - Click "Generate new token"
   - Scopes: `public_repo`, `read:user`
   - Copiar token

2. En `.env.local`:
```bash
EXPO_PUBLIC_GITHUB_TOKEN=tu_token_aqui
```

3. En `src/components/LabSection.tsx`:
```typescript
const token = process.env.EXPO_PUBLIC_GITHUB_TOKEN;
const headers = token 
  ? { 'Authorization': `token ${token}` } 
  : {};

const response = await fetch(url, { headers });
```

## Paso 9: Build para Producción

```bash
# Crear build estático
npm run build

# Esto crea la carpeta `dist/` lista para desplegar

# Probar localmente
npm run preview
# Abre http://localhost:3000
```

## 🎬 Ejemplos de Animaciones

### StackCarousel
- Swipe left/right con física (react-native-reanimated)
- Cartas se escalan y rotan suavemente
- Video autoplay cuando está activa

### ProjectsGrid
- Hover invierte la tarjeta (blanco ↔ negro)
- Reveal de detalles técnicos

### LabSection
- Entrada en cascada (staggered)
- Cada tarjeta aparece 100ms después de la anterior
- Efecto de deslizamiento suave desde abajo

## 🐛 Troubleshooting Rápido

**Error: "Cannot find module 'react-native-reanimated/plugin'"**
```bash
rm -rf node_modules package-lock.json
npm install
npx expo start --web --clear
```

**Video no se reproduce**
- ✅ Formato: .mp4 o .webm
- ✅ Bitrate < 5 Mbps
- ✅ URL accesible desde navegador
- ✅ CORS habilitado (si está en CDN diferente)

**Animaciones lentas**
- ✅ Usar worklets en useAnimatedStyle
- ✅ Evitar state dentro de useAnimatedStyle
- ✅ Reducir número de elementos animados

## 📊 Checklist Pre-Deploy

- [ ] Actualizé todos los proyectos en `projects.ts`
- [ ] Agregué URLs de videos optimizados
- [ ] Probé el carrusel con swipe
- [ ] Probé las grillas con hover/tap
- [ ] Verifiqué el GitHub feed en "The Lab"
- [ ] Testé en mobile (DevTools)
- [ ] Cambié nombre/enlaces personales
- [ ] Hice npm run build sin errores
- [ ] Probé npm run preview localmente
- [ ] Conecté repo a Vercel

## 🎉 ¡Listo!

Tu portafolio está configurado y listo. Ahora:

1. **Personaliza tus proyectos** en `src/constants/projects.ts`
2. **Sube videos optimizados** a tu CDN
3. **Deploy en Vercel** cuando esté listo
4. **Comparte el link** con el mundo

---

**Documentación completa:** Ver `README.md`
**Repo:** https://github.com/sebxdixz/sebastiandiaz.eeden.app
