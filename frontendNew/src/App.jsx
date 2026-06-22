import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/layout/Layout';
import DashboardPage from './pages/DashboardPage';
import EditorPage from './pages/EditorPage';
import FilesPage from './pages/FilesPage';
import LoginPage from './pages/LoginPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/editor/:id" element={<EditorPage />} />
        <Route path="/editor" element={<EditorPage />} />
        
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="files" element={<FilesPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
