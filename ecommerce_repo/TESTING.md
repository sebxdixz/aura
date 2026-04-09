# 🧪 Guía de Testing

## Testing Local Rápido

```bash
# 1. Asegurar que las dependencias estén instaladas
npm list react-native-reanimated

# 2. Limpiar y reiniciar
npx expo start --web --clear

# 3. En el navegador, verificar:
# - Hero section carga sin errores
# - Carrusel responde a gestos
# - Grilla de proyectos es visible
# - GitHub feed carga repositorios
```

## Testing del StackCarousel

1. **Desktop (con mouse):**
   - Abrir DevTools (F12)
   - Ir a Dispositivos → Tablet/Mobile
   - Probar drag left/right en la tarjeta superior
   - Verificar que el siguiente proyecto aparece

2. **Mobile (DevTools):**
   - Toggle Device Toolbar (Ctrl+Shift+M)
   - Cambiar a iPhone 12
   - Probar swipe izquierda/derecha
   - Ver animaciones suaves

3. **Esperado:**
   - Swipe left → siguiente proyecto
   - Swipe right → proyecto anterior
   - Velocidad alta + swipe → physics animation
   - Video de proyecto activo se reproduce
   - Video de proyecto inactivo está pausado

## Testing de Animaciones

### Verificar 60 FPS

```bash
# En DevTools (F12) → Performance
# 1. Click en grabar
# 2. Hacer swipe en el carrusel
# 3. Detener grabación
# 4. Verificar que los frames sean consistentes

# Esperado: ~16ms per frame (60 FPS)
# Inaceptable: >50ms per frame (menos de 20 FPS)
```

### Verificar Reanimated Worklets

Abrir DevTools Console:
```javascript
// Debería haber algo relacionado a Reanimated
console.log(global.jsSchedulingMode)
```

Si hay errores sobre "worklet", verificar `babel.config.js`

## Testing de Componentes

### StackCarousel
```javascript
// En DevTools Console, ejecutar:
const carousel = document.querySelector('[class*="cardWrapper"]');
console.log('Cards encontradas:', carousel?.parentElement?.children.length);
```

### ProjectsGrid (Hover/Invert)
- Desktop: Pasar mouse sobre tarjetas → deben invertirse
- Mobile: Tap en tarjeta → debe invertirse
- Verificar que el texto de detalles aparece invertido

### LabSection
- Scroll hasta la sección
- Verificar que repositorios cargan
- Verificar entrada en cascada (tarjetas no aparecen todas juntas)
- Click en tarjeta → abre GitHub en nueva pestaña

## Testing de Video

```javascript
// En DevTools Console
const video = document.querySelector('video');
console.log('Video status:');
console.log('- src:', video?.src);
console.log('- autoplay:', video?.autoplay);
console.log('- muted:', video?.muted);
console.log('- currentTime:', video?.currentTime);
```

**Troubleshooting:**
- Si `currentTime` es 0 → video no se reproduciendo
- Verificar CORS si está en CDN diferente
- Verificar que el bitrate es bajo (<5 Mbps)

## Testing de Responsive Design

```bash
npx expo start --web
```

Probar en:
- 1920x1080 (Desktop HD)
- 1280x800 (Laptop)
- 768x1024 (Tablet)
- 375x812 (iPhone 12)
- 360x640 (Android)

Verificar:
- [ ] Elementos no se salen de pantalla
- [ ] Texto es legible en todos los tamaños
- [ ] Botones son tocables (min 44x44 px)
- [ ] Animaciones funcionan en todos los tamaños

## Testing antes de Deploy

```bash
# 1. Build
npm run build

# 2. Verificar que no hay errores
# Debería crear carpeta `dist/` sin warnings

# 3. Preview local
npm run preview

# 4. Probar en http://localhost:3000
# Verificar que todo funciona igual que en dev

# 5. Lighthouse
# DevTools → Lighthouse
# Objetivo: 90+ en todas las categorías
```

## Performance Metrics

Usar DevTools → Lighthouse:

| Métrica | Objetivo | Aceptable |
|---------|----------|-----------|
| LCP | < 2.5s | < 3.5s |
| FID | < 100ms | < 300ms |
| CLS | < 0.1 | < 0.25 |

## Git Workflow Recomendado

```bash
# Crear rama para cambios
git checkout -b feature/mis-cambios

# Hacer cambios
# Testear localmente
npm run dev

# Si todo funciona:
git add .
git commit -m "feat: agregar mis proyectos"
git push origin feature/mis-cambios

# En GitHub: crear Pull Request
# Vercel deployará automáticamente para preview
```

## Checklist de Testing Final

- [ ] npm run dev funciona sin errores
- [ ] Carrusel responde a gestos
- [ ] Videos se reproducen correctamente
- [ ] Animaciones funcionan en 60 FPS
- [ ] GitHub feed carga repositorios
- [ ] Responsive funciona en mobile
- [ ] npm run build sin warnings
- [ ] npm run preview funciona
- [ ] Lighthouse 90+
- [ ] No hay warnings en console
