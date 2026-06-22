import React from 'react';
import { Loader2 } from 'lucide-react';
import styles from './Button.module.css';

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  icon: Icon,
  className = '',
  ...props
}) => {
  const baseClass = `${styles.btn} ${styles[variant]} ${styles[size]} ${className}`;
  
  return (
    <button 
      className={baseClass} 
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className={styles.spinner} size={16} />}
      {!loading && Icon && <Icon size={size === 'sm' ? 16 : 20} className={styles.icon} />}
      <span className={styles.text}>{children}</span>
    </button>
  );
};

export default Button;
