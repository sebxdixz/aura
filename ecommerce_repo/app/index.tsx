import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Platform,
  ScrollView,
} from 'react-native';
import StackCarousel from '../src/components/StackCarousel';
import ProjectsGrid from '../src/components/ProjectsGrid';
import LabSection from '../src/components/LabSection';
import { TRANSLATIONS, Lang } from '../src/constants/translations';
import { PROJECTS } from '../src/constants/projects';
import { PROFILE_META, RESUME_CONTENT } from '../src/constants/resume';

const SOCIAL_LINKS = {
  linkedin: 'https://www.linkedin.com/in/sebastiandiazti/',
  github: 'https://github.com/sebxdixz',
  email: 'sdiazdelafuente9@gmail.com',
};

const FONT_FAMILY = Platform.select({
  ios: 'System',
  android: 'Roboto',
  default: 'Roboto',
});

const PAGE_MIN_HEIGHT = Platform.OS === 'web' ? ('100vh' as any) : ('100%' as any);

function Bullet({ text }: { text: string }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={styles.bulletMark}>+</Text>
      <Text style={styles.bulletText}>{text}</Text>
    </View>
  );
}

export default function HomeScreen() {
  const [lang, setLang] = useState<Lang>('es');
  const t = TRANSLATIONS[lang];
  const resume = RESUME_CONTENT[lang];

  const localizedProjects = PROJECTS.map((project) => {
    const descKey = `${project.id}-desc` as keyof typeof t;
    return { ...project, description: t[descKey] || project.description };
  });

  const openLink = (url: string) => Linking.openURL(url);
  const openEmail = () => Linking.openURL(`mailto:${SOCIAL_LINKS.email}`);

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={styles.pageContent}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.canvas}>
        <View style={styles.langBar}>
          {(['es', 'en', 'de'] as Lang[]).map((l) => (
            <TouchableOpacity
              key={l}
              onPress={() => setLang(l)}
              style={[styles.langButton, lang === l && styles.langButtonActive]}
            >
              <Text style={[styles.langText, lang === l && styles.langTextActive]}>
                {l.toUpperCase()}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.hero}>
          <Text style={styles.kicker}>{t.heroKicker}</Text>
          <Text style={styles.name}>Sebastian Diaz</Text>
          <Text style={styles.role}>{t.role}</Text>
          <Text style={styles.bio}>{t.bio}</Text>

          <View style={styles.metaGrid}>
            <Text style={styles.metaText}>{PROFILE_META.location}</Text>
            <Text style={styles.metaText}>{PROFILE_META.phone}</Text>
            <Text style={styles.metaText}>{PROFILE_META.email}</Text>
            <Text style={styles.metaText}>{PROFILE_META.academicEmail}</Text>
          </View>

          <View style={styles.skillsRow}>
            {resume.coreSkills.map((skill) => (
              <View key={skill} style={styles.skillChip}>
                <Text style={styles.skillChipText}>{skill}</Text>
              </View>
            ))}
          </View>

          <View style={styles.socialRow}>
            <TouchableOpacity
              style={[styles.socialButton, styles.socialButtonPrimary]}
              onPress={() => openLink(SOCIAL_LINKS.linkedin)}
            >
              <Text style={[styles.socialText, styles.socialTextPrimary]}>LinkedIn</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.socialButton}
              onPress={() => openLink(SOCIAL_LINKS.github)}
            >
              <Text style={styles.socialText}>GitHub</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.socialButton} onPress={openEmail}>
              <Text style={styles.socialText}>Email</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.featuredProjects}</Text>
          <View style={styles.carouselFrame}>
            <StackCarousel lang={lang} />
          </View>
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.selectedWork}</Text>
          <ProjectsGrid projects={localizedProjects} />
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.workExperience}</Text>
          {resume.experience.map((item) => (
            <View key={`${item.company}-${item.role}`} style={styles.resumeBlock}>
              <View style={styles.resumeHead}>
                <View style={styles.resumeHeadMain}>
                  <Text style={styles.resumeTitle}>{item.role}</Text>
                  <Text style={styles.resumeSubtitle}>{item.company}</Text>
                  {item.location ? (
                    <Text style={styles.resumeSubtitle}>{item.location}</Text>
                  ) : null}
                </View>
                <Text style={styles.resumePeriod}>{item.period}</Text>
              </View>
              <View style={styles.bulletList}>
                {item.highlights.map((highlight) => (
                  <Bullet key={highlight} text={highlight} />
                ))}
              </View>
            </View>
          ))}
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.education}</Text>
          {resume.education.map((item) => (
            <View key={item.institution} style={styles.resumeBlock}>
              <View style={styles.resumeHead}>
                <View style={styles.resumeHeadMain}>
                  <Text style={styles.resumeTitle}>{item.institution}</Text>
                  <Text style={styles.resumeSubtitle}>{item.degree}</Text>
                  <Text style={styles.resumeSubtitle}>{item.title}</Text>
                </View>
                <Text style={styles.resumePeriod}>{item.period}</Text>
              </View>
              <View style={styles.bulletList}>
                {item.highlights.map((highlight) => (
                  <Bullet key={highlight} text={highlight} />
                ))}
              </View>
            </View>
          ))}
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.certifications}</Text>
          <View style={styles.resumeBlock}>
            {resume.certifications.map((cert, index) => (
              <View
                key={`${cert.provider}-${cert.name}`}
                style={[styles.certRow, index > 0 && styles.certRowBorder]}
              >
                <View style={styles.certMain}>
                  <Text style={styles.certName}>{cert.name}</Text>
                  <Text style={styles.certProvider}>{cert.provider}</Text>
                </View>
                <Text style={styles.certPeriod}>{cert.period}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.separator} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>{t.theLab}</Text>
          <LabSection lang={lang} />
        </View>

        <View style={styles.footer}>
          <View style={styles.footerLinks}>
            <TouchableOpacity onPress={() => openLink(SOCIAL_LINKS.linkedin)}>
              <Text style={styles.footerLink}>LinkedIn</Text>
            </TouchableOpacity>
            <Text style={styles.footerDot}> / </Text>
            <TouchableOpacity onPress={() => openLink(SOCIAL_LINKS.github)}>
              <Text style={styles.footerLink}>GitHub</Text>
            </TouchableOpacity>
            <Text style={styles.footerDot}> / </Text>
            <TouchableOpacity onPress={openEmail}>
              <Text style={styles.footerLink}>{SOCIAL_LINKS.email}</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.footerText}>{t.rights}</Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    width: '100%',
    backgroundColor: '#F6F6F4',
  },
  pageContent: {
    minHeight: PAGE_MIN_HEIGHT,
  },
  canvas: {
    width: '100%',
    maxWidth: 1240,
    alignSelf: 'center',
    paddingHorizontal: 20,
    paddingBottom: 48,
  },
  langBar: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 18,
    marginBottom: 26,
    gap: 8,
  },
  langButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: '#0F0F0F',
    borderRadius: 0,
    backgroundColor: '#F6F6F4',
  },
  langButtonActive: {
    backgroundColor: '#0F0F0F',
  },
  langText: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    color: '#0F0F0F',
    letterSpacing: 1,
  },
  langTextActive: {
    color: '#F6F6F4',
  },
  hero: {
    paddingBottom: 26,
  },
  kicker: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    color: '#4B4B4B',
    letterSpacing: 1.5,
    marginBottom: 12,
  },
  name: {
    fontFamily: FONT_FAMILY,
    fontSize: 72,
    lineHeight: 72,
    fontWeight: '900',
    color: '#0F0F0F',
  },
  role: {
    fontFamily: FONT_FAMILY,
    fontSize: 24,
    fontWeight: '700',
    color: '#1B1B1B',
    marginTop: 8,
  },
  bio: {
    marginTop: 16,
    maxWidth: 900,
    fontFamily: FONT_FAMILY,
    fontSize: 17,
    lineHeight: 28,
    color: '#2C2C2C',
  },
  metaGrid: {
    marginTop: 18,
    gap: 4,
  },
  metaText: {
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    fontWeight: '500',
    color: '#3A3A3A',
  },
  skillsRow: {
    marginTop: 18,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  skillChip: {
    borderWidth: 1,
    borderColor: '#0F0F0F',
    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: '#F6F6F4',
  },
  skillChipText: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '600',
    color: '#0F0F0F',
  },
  socialRow: {
    marginTop: 24,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  socialButton: {
    borderWidth: 1,
    borderColor: '#0F0F0F',
    borderRadius: 0,
    paddingHorizontal: 16,
    paddingVertical: 9,
    backgroundColor: '#F6F6F4',
  },
  socialButtonPrimary: {
    backgroundColor: '#0F0F0F',
  },
  socialText: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.6,
    color: '#0F0F0F',
  },
  socialTextPrimary: {
    color: '#F6F6F4',
  },
  separator: {
    height: 1,
    backgroundColor: '#1A1A1A',
  },
  section: {
    paddingVertical: 22,
  },
  sectionTitle: {
    fontFamily: FONT_FAMILY,
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -0.8,
    color: '#0F0F0F',
    marginBottom: 16,
  },
  carouselFrame: {
    borderWidth: 2,
    borderColor: '#0F0F0F',
    backgroundColor: '#000000',
    paddingVertical: 14,
    paddingHorizontal: 8,
    shadowColor: '#000000',
    shadowOpacity: 0.3,
    shadowRadius: 0,
    shadowOffset: { width: 4, height: 4 },
    elevation: 3,
  },
  resumeBlock: {
    borderWidth: 1,
    borderColor: '#0F0F0F',
    backgroundColor: '#FFFFFF',
    padding: 18,
    marginBottom: 12,
  },
  resumeHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
    flexWrap: 'wrap',
  },
  resumeHeadMain: {
    flex: 1,
    minWidth: 240,
  },
  resumeTitle: {
    fontFamily: FONT_FAMILY,
    fontSize: 24,
    fontWeight: '800',
    color: '#0F0F0F',
  },
  resumeSubtitle: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    fontWeight: '500',
    color: '#242424',
    marginTop: 3,
  },
  resumePeriod: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    color: '#0F0F0F',
    borderWidth: 1,
    borderColor: '#0F0F0F',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  bulletList: {
    marginTop: 14,
    gap: 8,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  bulletMark: {
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    fontWeight: '900',
    color: '#0F0F0F',
    marginTop: 1,
  },
  bulletText: {
    flex: 1,
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    lineHeight: 22,
    color: '#202020',
  },
  certRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
    paddingVertical: 10,
  },
  certRowBorder: {
    borderTopWidth: 1,
    borderTopColor: '#D3D3D3',
  },
  certMain: {
    flex: 1,
    minWidth: 220,
  },
  certName: {
    fontFamily: FONT_FAMILY,
    fontSize: 15,
    fontWeight: '700',
    color: '#0F0F0F',
  },
  certProvider: {
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    fontWeight: '500',
    color: '#3A3A3A',
    marginTop: 3,
  },
  certPeriod: {
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    fontWeight: '700',
    color: '#0F0F0F',
  },
  footer: {
    paddingTop: 26,
    alignItems: 'center',
  },
  footerLinks: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    alignItems: 'center',
  },
  footerLink: {
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    fontWeight: '600',
    color: '#0F0F0F',
  },
  footerDot: {
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    color: '#515151',
  },
  footerText: {
    marginTop: 10,
    fontFamily: FONT_FAMILY,
    fontSize: 12,
    color: '#515151',
  },
});
