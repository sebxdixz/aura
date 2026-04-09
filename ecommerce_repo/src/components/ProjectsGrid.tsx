import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  useWindowDimensions,
  Platform
} from 'react-native';
import { Project, PROJECTS } from '../constants/projects';

const FONT_FAMILY = Platform.select({
  ios: 'System',
  android: 'Roboto',
  default: 'Roboto',
});

interface ProjectGridItemProps {
  project: Project;
  itemWidth: number;
}

function ProjectGridItem({ project, itemWidth }: ProjectGridItemProps) {
  const [isInverted, setIsInverted] = useState(false);

  const handlePress = () => {
    setIsInverted(!isInverted);
  };

  return (
    <TouchableOpacity
      onPress={handlePress}
      style={[styles.gridItemContainer, { width: itemWidth }]}
      activeOpacity={0.8}
    >
      <View
        style={[
          styles.gridItem,
          { backgroundColor: isInverted ? '#000000' : '#FFFFFF' }
        ]}
      >
        {!isInverted ? (
          <Text style={[styles.gridItemTitle, { color: '#000000' }]}>
            {project.name}
          </Text>
        ) : (
          <View style={styles.gridItemDetails}>
            <Text style={styles.gridItemName}>{project.name}</Text>
            <Text style={styles.gridItemDesc}>{project.description}</Text>
            <View style={styles.gridItemTechs}>
              {project.techs.slice(0, 3).map((tech, idx) => (
                <View key={idx} style={styles.techBadge}>
                  <Text style={styles.gridItemTech}>{tech}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
}

interface ProjectsGridProps {
  projects?: Project[];
}

export default function ProjectsGrid({ projects = [] }: ProjectsGridProps) {
  const { width } = useWindowDimensions();
  const gridData: Project[] = projects.length > 0 ? projects : PROJECTS;
  const columns = width < 860 ? 1 : 2;
  const gutter = 16;
  const itemWidth = columns === 1 ? width - 80 : Math.max((width - 80 - gutter) / 2, 280);

  return (
    <View style={styles.container}>
      <View style={styles.grid}>
        {gridData.map((item) => (
          <ProjectGridItem key={item.id} project={item} itemWidth={itemWidth} />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%'
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 16
  },
  gridItemContainer: {
    height: 200,
    borderWidth: 1.5,
    borderColor: '#000000',
    borderRadius: 0,
    overflow: 'hidden'
  },
  gridItem: {
    flex: 1,
    padding: 16,
    justifyContent: 'center',
    alignItems: 'center'
  },
  gridItemTitle: {
    fontFamily: FONT_FAMILY,
    fontSize: 16,
    fontWeight: '700',
    textAlign: 'center'
  },
  gridItemDetails: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center'
  },
  gridItemName: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 8,
    textAlign: 'center'
  },
  gridItemDesc: {
    fontFamily: FONT_FAMILY,
    fontSize: 11,
    color: '#FFFFFF',
    marginBottom: 12,
    textAlign: 'center',
    lineHeight: 16
  },
  gridItemTechs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 4
  },
  techBadge: {
    borderWidth: 1,
    borderColor: '#FFFFFF',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 2
  },
  gridItemTech: {
    fontFamily: FONT_FAMILY,
    fontSize: 9,
    color: '#FFFFFF',
    fontWeight: '600'
  }
});
