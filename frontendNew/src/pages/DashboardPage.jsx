import React, { useState } from 'react';
import { Plus, MoreVertical, FileText, Trash2, Calendar, Edit3 } from 'lucide-react';
import { motion } from 'framer-motion';
import styles from './DashboardPage.module.css';
import Button from '../components/ui/Button';
import Modal from '../components/ui/Modal';
import { useNavigate } from 'react-router-dom';

const mockPapers = [
  { id: 1, title: 'Impact of AI on Modern Healthcare Systems', lastModified: '2 hours ago', status: 'Draft', wordCount: 4500 },
  { id: 2, title: 'Quantum Computing Algorithms for Encryption', lastModified: '1 day ago', status: 'Published', wordCount: 8200 },
  { id: 3, title: 'Sustainable Architecture in Urban Environments', lastModified: '3 days ago', status: 'Review', wordCount: 3100 },
];

const DashboardPage = () => {
  const navigate = useNavigate();
  const [papers, setPapers] = useState(mockPapers);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [paperToDelete, setPaperToDelete] = useState(null);

  const confirmDelete = (paper) => {
    setPaperToDelete(paper);
    setDeleteModalOpen(true);
  };

  const handleDelete = () => {
    setPapers(papers.filter(p => p.id !== paperToDelete.id));
    setDeleteModalOpen(false);
    // Trigger toast notification for soft-delete/undo here in real app
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Welcome back, Sirobo</h1>
          <p className={styles.subtitle}>Here's an overview of your recent research papers.</p>
        </div>
        <Button icon={Plus} onClick={() => navigate('/editor')}>Create New Paper</Button>
      </div>

      {papers.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}><FileText size={48} /></div>
          <h3>No papers yet</h3>
          <p>Start your research journey by creating your first paper.</p>
          <Button icon={Plus} onClick={() => navigate('/editor')} className={styles.emptyBtn}>Create First Paper</Button>
        </div>
      ) : (
        <div className={styles.grid}>
          {papers.map((paper, index) => (
            <motion.div 
              key={paper.id}
              className={styles.card}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <div className={styles.cardHeader}>
                <div className={`${styles.statusBadge} ${styles[paper.status.toLowerCase()]}`}>
                  {paper.status}
                </div>
                <button className={styles.moreBtn} aria-label="More options">
                  <MoreVertical size={18} />
                </button>
              </div>
              
              <div className={styles.cardBody}>
                <h3 className={styles.paperTitle}>{paper.title}</h3>
                <div className={styles.metaInfo}>
                  <span className={styles.metaItem}><Calendar size={14} /> {paper.lastModified}</span>
                  <span className={styles.metaItem}><FileText size={14} /> {paper.wordCount} words</span>
                </div>
              </div>

              <div className={styles.cardFooter}>
                <Button variant="secondary" size="sm" icon={Edit3} onClick={() => navigate(`/editor/${paper.id}`)}>
                  Continue Editing
                </Button>
                <button 
                  className={styles.deleteBtn} 
                  onClick={() => confirmDelete(paper)}
                  title="Move to Trash"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal - Fixing Critical UX Issue */}
      <Modal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Move to Trash"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteModalOpen(false)}>Cancel</Button>
            <Button variant="danger" icon={Trash2} onClick={handleDelete}>Move to Trash</Button>
          </>
        }
      >
        <p>Are you sure you want to move <strong>"{paperToDelete?.title}"</strong> to the trash?</p>
        <p className={styles.warningText}>You can restore it from the trash within 30 days.</p>
      </Modal>
    </div>
  );
};

export default DashboardPage;
