import React from 'react';
import { useUiStore } from '../../stores/useUiStore';
import styles from './LeftPane.module.css';

const LeftPane = ({ paperId }) => {
  const activeTab = useUiStore(state => state.getTab(paperId));

  return (
    <div className={styles.container}>
      {activeTab === 'editor' && (
        <div className={styles.content}>
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Title</h3>
            <p className={styles.mockContent}>Form editor for paper title goes here (Phase 2)</p>
          </div>
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Authors</h3>
            <p className={styles.mockContent}>Drag and drop authors list goes here (Phase 2)</p>
          </div>
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Sections</h3>
            <p className={styles.mockContent}>Nested sections drag and drop goes here (Phase 2)</p>
          </div>
        </div>
      )}

      {activeTab === 'preview' && (
        <div className={styles.content}>
          <div className={styles.previewCard}>
            <h2 className={styles.previewTitle}>Markdown Preview</h2>
            <p className={styles.mockContent}>Compiled paper output preview goes here</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default LeftPane;
