import React, { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import AppHeader from '../components/layout/AppHeader';
import EditorToolbar from '../components/editor/EditorToolbar';
import LeftPane from '../components/editor/LeftPane';
import RightPane from '../components/editor/RightPane';
import { useUiStore } from '../stores/useUiStore';
import { usePaperStore } from '../stores/usePaperStore';
import styles from './EditorPage.module.css';

const EditorPage = () => {
  const { id } = useParams();
  const paperId = id || 'paper-123';

  // State mapping
  const editorVisible = useUiStore(state => state.getEditorVisible(paperId));
  const toolsOpen = useUiStore(state => state.getToolsOpen(paperId));
  const rightPanel = useUiStore(state => state.getRightPanel(paperId));

  return (
    <div className={styles.container}>
      <AppHeader />
      <EditorToolbar paperId={paperId} />
      
      <div className={styles.splitRoot}>
        {editorVisible && (
          <div className={`${styles.leftPane} ${toolsOpen || rightPanel ? styles.wHalf : styles.wFull}`}>
            <LeftPane paperId={paperId} />
          </div>
        )}

        {(toolsOpen || rightPanel) && (
          <div className={`${styles.rightPane} ${editorVisible ? styles.wHalf : styles.wFull}`}>
            <RightPane paperId={paperId} />
          </div>
        )}
      </div>
    </div>
  );
};

export default EditorPage;
