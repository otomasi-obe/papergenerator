import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import styles from './Modal.module.css';
import Button from './Button';

const Modal = ({ 
  isOpen, 
  onClose, 
  title, 
  children, 
  footer, 
  maxWidth = '500px' 
}) => {
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose();
    };

    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className={styles.overlay} onClick={onClose} role="dialog" aria-modal="true">
          <motion.div 
            className={styles.modal} 
            style={{ maxWidth }}
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.2 }}
          >
            <div className={styles.header}>
              <h2 className={styles.title}>{title}</h2>
              <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
                <X size={20} />
              </button>
            </div>
            
            <div className={styles.content}>
              {children}
            </div>

            {footer && (
              <div className={styles.footer}>
                {footer}
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default Modal;
