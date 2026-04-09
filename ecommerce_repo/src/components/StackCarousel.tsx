import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  useWindowDimensions,
  TouchableOpacity,
  Text,
  Platform
} from 'react-native';
import ProjectCard from './ProjectCard';
import { PROJECTS } from '../constants/projects';
import { TRANSLATIONS, Lang } from '../constants/translations';

const FONT_FAMILY = Platform.select({
  ios: 'System',
  android: 'Roboto',
  default: 'Roboto',
});

interface StackCarouselProps {
  lang?: Lang;
}

export default function StackCarousel({ lang = 'es' }: StackCarouselProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const { width } = useWindowDimensions();
  const isCompact = width < 760;
  const t = TRANSLATIONS[lang];

  const handlePrev = () => {
    if (activeIndex > 0) setActiveIndex(activeIndex - 1);
  };

  const handleNext = () => {
    if (activeIndex < PROJECTS.length - 1) setActiveIndex(activeIndex + 1);
  };

  const project = PROJECTS[activeIndex];
  const descKey = `${project.id}-desc` as keyof typeof t;
  const translatedDesc = t[descKey] || project.description;

  return (
    <View style={styles.container}>
      <View style={styles.cardContainer}>
        <ProjectCard
          project={{ ...project, description: translatedDesc }}
          isActive={true}
          lang={lang}
        />
      </View>

      <View style={[styles.controls, isCompact && styles.controlsCompact]}>
        <TouchableOpacity
          style={[styles.button, isCompact && styles.buttonCompact, !activeIndex && styles.buttonDisabled]}
          onPress={handlePrev}
          disabled={activeIndex === 0}
        >
          <Text style={styles.buttonText}>{t.previous}</Text>
        </TouchableOpacity>

        <Text style={[styles.indicatorText, isCompact && styles.indicatorCompact]}>
          {activeIndex + 1} / {PROJECTS.length}
        </Text>

        <TouchableOpacity
          style={[
            styles.button,
            isCompact && styles.buttonCompact,
            activeIndex === PROJECTS.length - 1 && styles.buttonDisabled
          ]}
          onPress={handleNext}
          disabled={activeIndex === PROJECTS.length - 1}
        >
          <Text style={styles.buttonText}>{t.next}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.dots}>
        {PROJECTS.map((_, idx) => (
          <TouchableOpacity
            key={idx}
            style={[styles.dot, activeIndex === idx && styles.dotActive]}
            onPress={() => setActiveIndex(idx)}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'center',
    width: '100%',
    paddingBottom: 22,
    backgroundColor: '#000000'
  },
  cardContainer: {
    alignItems: 'center',
    marginBottom: 18,
    width: '100%'
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    width: '100%',
    paddingHorizontal: 12,
    marginBottom: 16,
    gap: 10
  },
  controlsCompact: {
    flexWrap: 'wrap',
    justifyContent: 'center'
  },
  button: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderWidth: 1.5,
    borderColor: '#F2F2F2',
    borderRadius: 0,
    backgroundColor: '#0A0A0A',
    shadowColor: '#000000',
    shadowOpacity: 0.4,
    shadowRadius: 0,
    shadowOffset: { width: 3, height: 3 },
    elevation: 2
  },
  buttonCompact: {
    minWidth: 120,
    alignItems: 'center'
  },
  buttonDisabled: {
    opacity: 0.3
  },
  buttonText: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    color: '#F2F2F2'
  },
  indicatorText: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    fontWeight: '700',
    color: '#F2F2F2'
  },
  indicatorCompact: {
    width: '100%',
    textAlign: 'center',
    marginVertical: 4
  },
  dots: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#1C1C1C',
    borderWidth: 1,
    borderColor: '#F2F2F2'
  },
  dotActive: {
    backgroundColor: '#F2F2F2',
    width: 10,
    height: 10,
    borderRadius: 5
  }
});
