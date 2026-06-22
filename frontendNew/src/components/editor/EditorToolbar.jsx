import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Undo, Redo, FileText, Settings, LayoutPanelLeft } from 'lucide-react';
import { useUiStore } from '../../stores/useUiStore';
import { usePaperStore } from '../../stores/usePaperStore';
import styles from './EditorToolbar.module.css';

const EditorToolbar = ({ paperId }) => {
  const navigate = useNavigate();
  const paper = usePaperStore(state => state.paper);
  const setPaperTitle = usePaperStore(state => state.setPaperTitle);
  const loading = usePaperStore(state => state.loading);
  const pendingCount = usePaperStore(state => state.pendingCount);

  // UI state
  const activeTab = useUiStore(state => state.getTab(paperId));
  const setActiveTab = useUiStore(state => state.setTab);
  const editorVisible = useUiStore(state => state.getEditorVisible(paperId));
  const setEditorVisible = useUiStore(state => state.setEditorVisible);
  const toolsOpen = useUiStore(state => state.getToolsOpen(paperId));
  const setToolsOpen = useUiStore(state => state.setToolsOpen);
  const rightPanel = useUiStore(state => state.getRightPanel(paperId));
  const setRightPanel = useUiStore(state => state.setRightPanel);

  const toggleEditor = () => {
    if (activeTab === 'editor' && editorVisible) {
      setEditorVisible(paperId, false);
      if (!toolsOpen && !rightPanel) setToolsOpen(paperId, true);
    } else {
      setEditorVisible(paperId, true);
      setActiveTab(paperId, 'editor');
    }
  };

  const togglePreview = () => {
    if (activeTab === 'preview' && editorVisible) {
      setEditorVisible(paperId, false);
      if (!toolsOpen && !rightPanel) setToolsOpen(paperId, true);
    } else {
      setEditorVisible(paperId, true);
      setActiveTab(paperId, 'preview');
    }
  };

  const toggleTools = () => {
    if (toolsOpen) {
      setToolsOpen(paperId, false);
      if (!rightPanel) setEditorVisible(paperId, true);
    } else {
      setRightPanel(paperId, '');
      setToolsOpen(paperId, true);
    }
  };

  return (
    <div className={styles.toolbar}>
      <div className={styles.container}>
        <div className={styles.leftGroup}>
          <button 
            className={styles.backBtn}
            onClick={() => navigate('/dashboard')}
          >
            <ArrowLeft size={16} />
            <span>Papers</span>
          </button>
          <span className={styles.divider}>|</span>
          <input 
            value={paper?.title || ''}
            onChange={(e) => setPaperTitle(e.target.value)}
            placeholder="Untitled Paper"
            className={styles.titleInput}
          />
          {loading ? (
            <span className={styles.saveStatus}>Saving...</span>
          ) : (
            <span className={styles.saveStatus}>Saved just now</span>
          )}
        </div>

        <div className={styles.rightGroup}>
          <div className={styles.actionBtns}>
            <button className={styles.actionBtn} title="Export DOCX">📄 DOCX</button>
            <button className={styles.actionBtn} title="Undo">↶ Undo</button>
            <button className={styles.actionBtn} title="Redo">↷ Redo</button>
            {pendingCount > 0 && (
              <span className={styles.pendingBadge}>{pendingCount} pending</span>
            )}
          </div>

          <div className={styles.toggleGroup}>
            <button 
              onClick={toggleEditor}
              className={`${styles.toggleBtn} ${activeTab === 'editor' && editorVisible ? styles.active : ''}`}
            >
              📝 Editor
            </button>
            <button 
              onClick={togglePreview}
              className={`${styles.toggleBtn} ${activeTab === 'preview' && editorVisible ? styles.active : ''}`}
            >
              👁 Preview
            </button>
            <button 
              onClick={toggleTools}
              className={`${styles.toggleBtn} ${toolsOpen || rightPanel ? styles.active : ''}`}
            >
              🛠 Tools
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EditorToolbar;
