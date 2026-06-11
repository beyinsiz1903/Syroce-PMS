import React from 'react';
import { Stack } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

// File-based stack routing for the shared Departments area. Sibling
// department screens (Accounting / Maintenance, future tasks) can be added
// as new files in this folder WITHOUT touching role routing or this layout.
export default function DepartmentsLayout() {
  const c = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: c.surface },
        headerTitleStyle: { color: c.text },
        headerTintColor: c.text,
        contentStyle: { backgroundColor: c.bg },
      }}
    >
      <Stack.Screen name="index" options={{ title: tr.departments.title }} />
      <Stack.Screen name="spa" options={{ title: tr.departments.spa.title }} />
      <Stack.Screen name="mice/index" options={{ title: tr.departments.mice.title }} />
      <Stack.Screen name="mice/[id]" options={{ title: tr.departments.mice.eventDetail }} />
      <Stack.Screen name="cashier" options={{ title: tr.departments.cashier.title }} />
      <Stack.Screen name="accounting" options={{ title: tr.departments.accounting.title }} />
      <Stack.Screen name="maintenance" options={{ title: tr.departments.maintenance.title }} />
      <Stack.Screen name="procurement" options={{ title: tr.departments.procurement.title }} />
      <Stack.Screen name="hr" options={{ title: tr.departments.hr.title }} />
      <Stack.Screen name="revenue" options={{ title: tr.departments.revenue.title }} />
    </Stack>
  );
}
