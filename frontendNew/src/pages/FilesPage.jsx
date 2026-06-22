import React, { useState } from 'react';
import { UploadCloud, FileImage, Trash2, Search, Filter } from 'lucide-react';
import { motion } from 'framer-motion';
import styles from './FilesPage.module.css';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Modal from '../components/ui/Modal';

const mockImages = [
  { id: 1, name: 'fig1-architecture.png', size: '1.2 MB', date: '2026-05-20', url: 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=400&q=80' },
  { id: 2, name: 'chart-results.svg', size: '45 KB', date: '2026-05-21', url: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400&q=80' },
  { id: 3, name: 'system-diagram.jpg', size: '2.4 MB', date: '2026-05-22', url: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=400&q=80' },
];

const FilesPage = () => {
  const [images, setImages] = useState(mockImages);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [imageToDelete, setImageToDelete] = useState(null);

  const confirmDelete = (img) => {
    setImageToDelete(img);
    setDeleteModalOpen(true);
  };

  const handleDelete = () => {
    setImages(images.filter(i => i.id !== imageToDelete.id));
    setDeleteModalOpen(false);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Assets & Files</h1>
          <p className={styles.subtitle}>Manage images and documents for your papers.</p>
        </div>
      </div>

      <div className={styles.toolbar}>
        <div className={styles.searchBox}>
          <Input placeholder="Search files..." icon={Search} className={styles.searchInput} />
        </div>
        <Button variant="secondary" icon={Filter}>Filter</Button>
      </div>

      <div className={styles.uploadZone}>
        <UploadCloud size={48} className={styles.uploadIcon} />
        <h3>Click or drag files to upload</h3>
        <p>Supports PNG, JPG, SVG, WebP (Max 5MB)</p>
        <Button className={styles.uploadBtn}>Select Files</Button>
      </div>

      <div className={styles.grid}>
        {images.map((img, index) => (
          <motion.div 
            key={img.id}
            className={styles.imageCard}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.1 }}
          >
            <div className={styles.imageWrapper}>
              <img src={img.url} alt={img.name} className={styles.thumbnail} loading="lazy" />
              <div className={styles.imageOverlay}>
                <button 
                  className={styles.deleteOverlayBtn} 
                  onClick={() => confirmDelete(img)}
                  aria-label="Delete image"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
            <div className={styles.imageMeta}>
              <div className={styles.imageName} title={img.name}>
                <FileImage size={16} className={styles.fileIcon} />
                {img.name}
              </div>
              <div className={styles.imageSize}>{img.size} • {img.date}</div>
            </div>
          </motion.div>
        ))}
      </div>

      <Modal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Delete File"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteModalOpen(false)}>Cancel</Button>
            <Button variant="danger" icon={Trash2} onClick={handleDelete}>Delete Permanently</Button>
          </>
        }
      >
        <p>Are you sure you want to permanently delete <strong>"{imageToDelete?.name}"</strong>?</p>
        <p className={styles.warningText}>This action cannot be undone and may break references in your papers.</p>
      </Modal>
    </div>
  );
};

export default FilesPage;
