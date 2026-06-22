import React from 'react';
import { useUiStore } from '../../stores/useUiStore';
import { MessageSquare, BookOpen, FileText, BarChart2, Image as ImageIcon, Briefcase } from 'lucide-react';
import styles from './RightPane.module.css';

const RightPane = ({ paperId }) => {
  const toolsOpen = useUiStore(state => state.getToolsOpen(paperId));
  const rightPanel = useUiStore(state => state.getRightPanel(paperId));
  const setRightPanel = useUiStore(state => state.setRightPanel);
  const setToolsOpen = useUiStore(state => state.setToolsOpen);
  const setEditorVisible = useUiStore(state => state.setEditorVisible);

  const openPanel = (panel) => {
    setToolsOpen(paperId, false);
    setRightPanel(paperId, panel);
    // Don't force editor open, respect user's choice
  };

  if (toolsOpen) {
    return (
      <div className={styles.toolsMenu}>
        <div className={styles.menuContainer}>
          <button className={styles.menuItem} onClick={() => openPanel('paperfull')}>
            <FileText size={18} />
            <span>Paperfull</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('chat')}>
            <MessageSquare size={18} />
            <span>AI Chat</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('journal')}>
            <BookOpen size={18} />
            <span>Journal</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('literature')}>
            <BookOpen size={18} />
            <span>Literature</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('files')}>
            <FileText size={18} />
            <span>Files</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('data')}>
            <BarChart2 size={18} />
            <span>Data</span>
          </button>
          <button className={styles.menuItem} onClick={() => openPanel('image')}>
            <ImageIcon size={18} />
            <span>Image</span>
          </button>
          
          <div className={styles.divider}></div>
          
          <button className={styles.menuItem} onClick={() => openPanel('tool-workspace')}>
            <Briefcase size={18} />
            <span>Tool Workspace</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.panelContainer}>
      <div className={styles.panelHeader}>
        <h3 className={styles.panelTitle}>
          {rightPanel.charAt(0).toUpperCase() + rightPanel.slice(1)}
        </h3>
        <button 
          className={styles.closeBtn}
          onClick={() => {
            setRightPanel(paperId, '');
            setEditorVisible(paperId, true);
          }}
        >
          ✕
        </button>
      </div>
      <div className={styles.panelContent}>
        <p className={styles.mockContent}>
          {rightPanel} implementation goes here (Phase 3)
        </p>
      </div>
    </div>
  );
};

export default RightPane;
