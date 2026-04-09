import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Platform,
  useWindowDimensions
} from 'react-native';
import { Project } from '../constants/projects';
import { Lang, TRANSLATIONS } from '../constants/translations';

const FONT_FAMILY = Platform.select({
  ios: 'System',
  android: 'Roboto',
  default: 'Roboto',
});

interface ProjectCardProps {
  project: Project;
  isActive: boolean;
  lang?: Lang;
}

export default function ProjectCard({ project, lang = 'es' }: ProjectCardProps) {
  const { width } = useWindowDimensions();
  const cardWidth = Math.min(Math.max(width - 70, 280), 980);
  const t = TRANSLATIONS[lang];

  const isAIAgent = project.techs.some((tech) =>
    tech.toLowerCase().includes('ai') ||
    tech.toLowerCase().includes('agent') ||
    tech.toLowerCase().includes('claude')
  );

  const primaryLink =
    project.links.website ||
    project.links.demo ||
    project.links.github;

  const handleViewProject = () => {
    if (primaryLink) {
      Linking.openURL(primaryLink);
    }
  };

  return (
    <View style={[styles.card, { width: cardWidth }]}>
      <View style={styles.overlay}>
        <View style={styles.content}>
          <View style={styles.headerRow}>
            <Text style={styles.projectName}>{project.name}</Text>
            {isAIAgent && (
              <View style={styles.agentBadge}>
                <Text style={styles.agentBadgeText}>{t.aiAgent}</Text>
              </View>
            )}
          </View>
          <Text style={styles.projectDescription}>{project.description}</Text>

          <View style={styles.techStack}>
            {project.techs.map((tech, idx) => (
              <View key={idx} style={styles.techTag}>
                <Text style={styles.techText}>{tech}</Text>
              </View>
            ))}
          </View>

          {primaryLink && (
            <TouchableOpacity
              style={styles.ctaButton}
              onPress={handleViewProject}
              activeOpacity={0.8}
            >
              <Text style={styles.ctaText}>
                {project.links.website || project.links.demo ? t.visit : t.viewOnGithub}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    height: 520,
    backgroundColor: '#000000',
    borderRadius: 0,
    overflow: 'hidden',
    borderWidth: 1.5,
    borderColor: '#F2F2F2'
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
    paddingHorizontal: 24,
    paddingVertical: 32
  },
  content: {
    width: '100%'
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 12
  },
  projectName: {
    fontFamily: FONT_FAMILY,
    fontSize: 34,
    fontWeight: '900',
    color: '#FFFFFF',
    flex: 1
  },
  agentBadge: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 20,
    minWidth: 90,
    alignItems: 'center',
    justifyContent: 'center'
  },
  agentBadgeText: {
    fontFamily: FONT_FAMILY,
    fontSize: 11,
    fontWeight: '700',
    color: '#000000'
  },
  projectDescription: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    color: '#FFFFFF',
    marginBottom: 24,
    lineHeight: 22
  },
  techStack: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 24
  },
  techTag: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    marginRight: 8,
    marginBottom: 8
  },
  techText: {
    fontFamily: FONT_FAMILY,
    fontSize: 11,
    fontWeight: '600',
    color: '#000000'
  },
  ctaButton: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 0,
    alignItems: 'center'
  },
  ctaText: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    fontWeight: '700',
    color: '#000000'
  }
});
