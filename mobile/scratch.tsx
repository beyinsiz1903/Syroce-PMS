  const renderSpaGymTab = () => {
    const data = spaReservationsQ.data || [];
    const showList = !spaReservationsQ.isLoading && !spaReservationsQ.error && data.length > 0;
    return (
      <View>
        <SectionTitle title="SPA & Spor Salonu" />
        <Muted>SPA Randevuları ve Kaynak Planlama</Muted>
        <View style={{ height: spacing.sm }} />
        {!showList ? (
          <DepartmentListState
            loading={spaReservationsQ.isLoading}
            error={spaReservationsQ.error}
            isEmpty={data.length === 0}
            emptyText="SPA rezervasyonu bulunamadı."
          />
        ) : (
          <ListGroup>
            {data.map((r, idx) => (
              <ListRow
                key={r.id}
                icon="leaf-outline"
                label={r.guest_name}
                sublabel={`${r.res_date} ${r.res_time} | Süre: ${r.duration_minutes} dk`}
                last={idx === data.length - 1}
                right={<Badge label={statusLabel(r.status)} tone={statusTone(r.status)} />}
                onPress={() => setSelectedSpaReservation(r)}
              />
            ))}
          </ListGroup>
        )}
      </View>
    );
  };
