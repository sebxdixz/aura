# 🚀 START HERE

## Tu portafolio está listo. Sigue estos pasos:

### 1️⃣ Abre tu proyecto
```bash
cd "C:\Users\sdiaz\OneDrive - Axo\Escritorio\Personal\portfolio"
```

### 2️⃣ Inicia desarrollo local
```bash
npm run dev
```
Esto abre automáticamente http://localhost:8081

### 3️⃣ Personaliza tus proyectos
Edita este archivo:
```
src/constants/projects.ts
```

Cambia esto:
```typescript
export const PROJECTS: Project[] = [
  {
    id: 'proyecto-1',
    name: 'MI PROYECTO',           // ← Cambia
    description: 'Mi descripción', // ← Cambia
    videoUrl: 'https://...',       // ← Agrega URL de video
    techs: ['React', 'TypeScript'], // ← Tus tecnologías
    links: {
      github: 'https://...',
      website: 'https://...'
    }
  }
  // ... más proyectos
];
```

### 4️⃣ Optimiza tus videos
```bash
# Convertir a MP4 con bajo bitrate
ffmpeg -i input.mov -b:v 2M -b:a 128k output.mp4
```
Sube a: Cloudinary, Vercel, o tu CDN

### 5️⃣ Deploy en Vercel
1. Ir a https://vercel.com/new
2. Conectar GitHub
3. Vercel auto-detecta Expo
4. Click "Deploy"

---

## 📚 Documentación
- **QUICK_START.txt** - Guía rápida (5 min)
- **SETUP.md** - Guía completa (20 min)
- **TESTING.md** - Cómo testear

## 💡 Tips
- **Swipe test**: En el navegador, drag izquierda/derecha en la tarjeta
- **Hover test**: Pasa mouse sobre proyectos de la grilla
- **GitHub feed**: Automático, muestra tus repos

## ❓ Problemas?
- Video no se reproduce → convertir a .mp4, bitrate < 5 Mbps
- Animaciones lentas → npm run dev --clear
- GitHub API error → agregar token en .env.local

---

**¡Listo! Empieza con `npm run dev`** 🎉
