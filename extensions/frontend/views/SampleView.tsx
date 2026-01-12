/**
 * Sample View Component
 * 
 * Demonstrates M8Flow extension capabilities with a custom page
 */

import React from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Chip,
} from '@mui/material';
import { Extension, Dashboard, Settings, Code } from '@mui/icons-material';

export const SampleView: React.FC = () => {
  const features = [
    {
      title: 'Extension System',
      description: 'Plugin-based architecture for seamless customization',
      icon: <Extension sx={{ fontSize: 40 }} />,
      color: '#667eea',
    },
    {
      title: 'Custom Views',
      description: 'Create custom pages and routes without touching upstream code',
      icon: <Dashboard sx={{ fontSize: 40 }} />,
      color: '#764ba2',
    },
    {
      title: 'Build Variants',
      description: 'Switch between Spiff and M8Flow builds with environment config',
      icon: <Settings sx={{ fontSize: 40 }} />,
      color: '#f093fb',
    },
    {
      title: 'Zero-Touch',
      description: '100% upstream isolation - no modifications to SpiffWorkflow code',
      icon: <Code sx={{ fontSize: 40 }} />,
      color: '#4facfe',
    },
  ];

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom>
          Welcome to M8Flow Extensions
        </Typography>
        <Typography variant="h6" color="text.secondary" paragraph>
          This is a sample page demonstrating the M8Flow extension system
        </Typography>
        <Chip label="Extension Active" color="success" sx={{ mt: 2 }} />
      </Box>

      <Grid container spacing={3}>
        {features.map((feature, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card
              sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                transition: 'transform 0.2s',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: 4,
                },
              }}
            >
              <CardHeader
                avatar={
                  <Box
                    sx={{
                      color: feature.color,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {feature.icon}
                  </Box>
                }
              />
              <CardContent>
                <Typography variant="h6" component="h2" gutterBottom>
                  {feature.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {feature.description}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 4, p: 3, bgcolor: 'background.default', borderRadius: 2 }}>
        <Typography variant="h6" gutterBottom>
          Development Tips
        </Typography>
        <Typography variant="body2" component="div">
          <ul>
            <li>All custom code lives in <code>extensions/frontend/</code></li>
            <li>Upstream code in <code>spiffworkflow-frontend/</code> remains untouched</li>
            <li>Use <code>npm start</code> from <code>extensions/frontend/</code> to run with extensions</li>
            <li>Hot Module Replacement (HMR) works for rapid development</li>
          </ul>
        </Typography>
      </Box>
    </Container>
  );
};

export default SampleView;
