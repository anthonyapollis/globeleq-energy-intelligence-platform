/*
=============================================================
Baobab Power Energy Intelligence Platform
V2 Upgrade: Meter Data Quality + Forecast Model Registry
=============================================================
Run AFTER baobab_power_energy_dw.sql.
Adds 9 new tables and 6 new BI views without modifying
any existing tables, columns, constraints or indexes.

New tables
  dw.DimTime                     — hour-of-day dimension (0–23)
  dw.DimMeter                    — meter registry per plant
  dw.DimForecastModel            — model registry (3 Terra Firma + 5 ML models)
  dw.DimForecastFeature          — technology-specific driver features
  dw.BridgeForecastModelFeature  — model-to-feature many-to-many
  dw.FactMeterReadingHourly      — raw / clean / quality hourly readings
  dw.FactDataQualityEvent        — immutable audit log of every DQ event
  dw.FactForecastDaily           — per-plant daily forecasts with bounds
  dw.FactForecastModelValidation — MAE / RMSE / sMAPE / R² / bias per model-plant
  dw.FactWeatherNormalisedPerf   — weather-normalised generation vs actual

New BI views
  bi.vw_MeterDataQuality
  bi.vw_ForecastVsActual
  bi.vw_ModelScorecard
  bi.vw_WeatherNormalisedPerf
  bi.vw_DataQualityEvents
  bi.vw_ForecastModelRegistry
=============================================================
*/
USE BaobabPowerEnergyDW;
GO

-- ============================================================
-- SECTION 1 — DimTime (hour-of-day lookup)
-- ============================================================
IF OBJECT_ID(N'dw.DimTime', N'U') IS NULL
BEGIN
    CREATE TABLE dw.DimTime
    (
        TimeKey         TINYINT         NOT NULL PRIMARY KEY,   -- 0 – 23
        HourLabel       NVARCHAR(10)    NOT NULL,               -- "00:00", "01:00" …
        DayPart         NVARCHAR(20)    NOT NULL,               -- Night / Morning / Afternoon / Evening
        IsPeakHour      BIT             NOT NULL,               -- 07:00–21:00 = 1
        HourBlock4      NVARCHAR(10)    NOT NULL,               -- "00-06", "06-12", "12-18", "18-24"
        CONSTRAINT UQ_DimTime UNIQUE (HourLabel)
    );

    INSERT INTO dw.DimTime (TimeKey, HourLabel, DayPart, IsPeakHour, HourBlock4)
    VALUES
        ( 0,'00:00','Night',    0,'00-06'),( 1,'01:00','Night',    0,'00-06'),
        ( 2,'02:00','Night',    0,'00-06'),( 3,'03:00','Night',    0,'00-06'),
        ( 4,'04:00','Night',    0,'00-06'),( 5,'05:00','Night',    0,'00-06'),
        ( 6,'06:00','Morning',  0,'06-12'),( 7,'07:00','Morning',  1,'06-12'),
        ( 8,'08:00','Morning',  1,'06-12'),( 9,'09:00','Morning',  1,'06-12'),
        (10,'10:00','Morning',  1,'06-12'),(11,'11:00','Morning',  1,'06-12'),
        (12,'12:00','Afternoon',1,'12-18'),(13,'13:00','Afternoon',1,'12-18'),
        (14,'14:00','Afternoon',1,'12-18'),(15,'15:00','Afternoon',1,'12-18'),
        (16,'16:00','Afternoon',1,'12-18'),(17,'17:00','Afternoon',1,'12-18'),
        (18,'18:00','Evening',  1,'18-24'),(19,'19:00','Evening',  1,'18-24'),
        (20,'20:00','Evening',  1,'18-24'),(21,'21:00','Evening',  1,'18-24'),
        (22,'22:00','Evening',  0,'18-24'),(23,'23:00','Night',    0,'18-24');
END;
GO

-- ============================================================
-- SECTION 2 — DimMeter (meter registry)
-- ============================================================
IF OBJECT_ID(N'dw.DimMeter', N'U') IS NULL
BEGIN
    CREATE TABLE dw.DimMeter
    (
        MeterKey        INT             NOT NULL PRIMARY KEY,
        PlantKey        INT             NOT NULL,
        MeterCode       NVARCHAR(50)    NOT NULL,
        MeterName       NVARCHAR(200)   NOT NULL,
        MeterType       NVARCHAR(50)    NOT NULL,   -- Revenue / Check / Grid / Plant
        MeasurementUnit NVARCHAR(20)    NOT NULL,   -- MWh / MW / kWh
        SourceSystem    NVARCHAR(100)   NULL,        -- SCADA / ERP / Smart-Meter
        InstallDate     DATE            NULL,
        IsActive        BIT             NOT NULL CONSTRAINT DF_DimMeter_IsActive DEFAULT (1),
        CONSTRAINT UQ_DimMeter_Code UNIQUE (MeterCode),
        CONSTRAINT FK_DimMeter_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
    );

    -- Seed one revenue meter per operating plant (PlantKey 1–17)
    INSERT INTO dw.DimMeter (MeterKey, PlantKey, MeterCode, MeterName, MeterType, MeasurementUnit, SourceSystem, InstallDate, IsActive)
    SELECT
        PlantKey AS MeterKey,
        PlantKey,
        CONCAT('MTR-', UPPER(PlantCode), '-REV') AS MeterCode,
        CONCAT(PlantName, ' Revenue Meter')       AS MeterName,
        'Revenue'                                  AS MeterType,
        'MWh'                                      AS MeasurementUnit,
        'SCADA'                                    AS SourceSystem,
        '2020-01-01'                               AS InstallDate,
        1                                          AS IsActive
    FROM dw.DimPlant
    WHERE PlantKey <= 17;
END;
GO

-- ============================================================
-- SECTION 3 — DimForecastModel
-- ============================================================
IF OBJECT_ID(N'dw.DimForecastModel', N'U') IS NULL
BEGIN
    CREATE TABLE dw.DimForecastModel
    (
        ForecastModelKey        INT             NOT NULL PRIMARY KEY,
        ModelName               NVARCHAR(200)   NOT NULL,
        ModelFamily             NVARCHAR(100)   NOT NULL,
        ModelVersion            NVARCHAR(20)    NOT NULL,
        TrainingPeriodStart     DATE            NOT NULL,
        TrainingPeriodEnd       DATE            NOT NULL,
        ValidationPeriodStart   DATE            NOT NULL,
        ValidationPeriodEnd     DATE            NOT NULL,
        PrimaryFeatures         NVARCHAR(1000)  NOT NULL,
        RetrainingFrequency     NVARCHAR(50)    NOT NULL,
        IsRecursiveForecast     BIT             NOT NULL,
        ModelStatus             NVARCHAR(30)    NOT NULL,   -- Active / Retired / Candidate
        IsSelectedModel         BIT             NOT NULL,
        SelectionCriteria       NVARCHAR(200)   NULL,
        Notes                   NVARCHAR(1000)  NULL,
        CONSTRAINT CK_DimForecastModel_Status CHECK (ModelStatus IN ('Active','Retired','Candidate'))
    );

    INSERT INTO dw.DimForecastModel VALUES
    -- Terra Firma-sourced forecasting models
    (1, 'Weekly Seasonal Profile',
     'Seasonal Decomposition',    '1.0',
     '2020-01-01','2023-12-31',   '2024-01-01','2024-12-31',
     'DayOfWeek, HourOfDay, MonthOfYear, PublicHoliday, Historical 52-week median',
     'Monthly', 1, 'Active', 0,
     'Lowest RMSE tie-breaker: lowest absolute total forecast bias',
     'Baseline seasonal model. Strong on stable profiles; limited on weather-driven plants.'),
    (2, 'Robust Dynamic Regression',
     'Regression',                '1.0',
     '2020-01-01','2023-12-31',   '2024-01-01','2024-12-31',
     'GHI, WindSpeedMs, AmbientTempC, HourOfDay, PlantAvailability, Lag1h, Lag24h',
     'Quarterly', 0, 'Active', 0,
     'Lowest RMSE tie-breaker: lowest absolute total forecast bias',
     'Uses MM-estimator for outlier robustness. Handles sensor faults in training data.'),
    (3, 'Technology-Aware Weather GBM',
     'Gradient Boosting',         '1.0',
     '2020-01-01','2023-12-31',   '2024-01-01','2024-12-31',
     'Technology-specific: GHI/WindSpeed/SteamPressure, AvailabilityPct, CurtailmentPct, '
     + 'WakeEffect, AirDensity, InverterTemp, DispatchInstruction, HeatRate, Lag1h/24h/168h',
     'Monthly', 0, 'Active', 1,
     'Lowest RMSE tie-breaker: lowest absolute total forecast bias',
     'Selected model. Uses technology-specific feature sets. Lowest portfolio-level RMSE.'),
    -- Existing MLflow models (energy, operations, commercial)
    (4, 'XGBoost Energy Yield Forecaster',
     'Gradient Boosting', '1.0',
     '2020-01-01','2023-12-31', '2024-01-01','2024-12-31',
     'GHI, WindSpeedMs, AmbientTempC, HourOfDay, Month, PlantKey, CapacityMW',
     'Quarterly', 0, 'Active', 0,
     'R² optimised', 'R²=0.94, MAE=18 MWh'),
    (5, 'LightGBM Forced Outage Predictor',
     'Gradient Boosting Classifier', '1.0',
     '2020-01-01','2023-12-31', '2024-01-01','2024-12-31',
     'AvailabilityPct_7d, ForcedDowntimeHours_Lag7, TransformerTempC, MaintenanceCost_Lag30',
     'Monthly', 0, 'Active', 0,
     'AUC / Recall (threshold=0.35)', 'AUC=0.82, scale_pos_weight=11x'),
    (6, 'Random Forest Maintenance Cost Estimator',
     'Random Forest', '1.0',
     '2020-01-01','2023-12-31', '2024-01-01','2024-12-31',
     'WorkOrderType, Priority, PlantKey, AssetType, LabourHours, ForcedDowntimeHours_Lag30',
     'Quarterly', 0, 'Active', 0,
     'R² optimised', 'R²=0.89, OOB=0.87'),
    (7, 'Isolation Forest Curtailment Anomaly Detector',
     'Anomaly Detection', '1.0',
     '2020-01-01','2023-12-31', '2024-01-01','2024-12-31',
     'ActivePowerMW, GridFrequencyHz, TransformerTempC, CurtailmentFactor, AmbientTempC',
     'Monthly', 0, 'Active', 0,
     'Contamination rate', 'Anomaly rate=5%, contamination=0.05'),
    (8, 'LightGBM Portfolio Revenue Forecaster',
     'Gradient Boosting', '1.0',
     '2020-01-01','2023-12-31', '2024-01-01','2024-12-31',
     'EnergySoldMWh, USDZAR_Rate, AvailabilityPct, ContractedTariffUSD, Rev_Lag1/3/12',
     'Monthly', 0, 'Active', 0,
     'RMSE / MAPE optimised', 'R²=0.93, MAPE=3.1%');
END;
GO

-- ============================================================
-- SECTION 4 — DimForecastFeature
-- ============================================================
IF OBJECT_ID(N'dw.DimForecastFeature', N'U') IS NULL
BEGIN
    CREATE TABLE dw.DimForecastFeature
    (
        ForecastFeatureKey  INT             NOT NULL PRIMARY KEY,
        FeatureName         NVARCHAR(100)   NOT NULL,
        TechnologyGroup     NVARCHAR(50)    NOT NULL,   -- Solar / Wind / Gas-HFO / Geothermal / BESS / All
        FeatureCategory     NVARCHAR(50)    NOT NULL,   -- Weather / Operational / Commercial / Temporal
        FeatureDescription  NVARCHAR(500)   NOT NULL,
        IsApplicableForPowerForecasting BIT NOT NULL,
        CONSTRAINT UQ_DimForecastFeature UNIQUE (FeatureName, TechnologyGroup)
    );

    INSERT INTO dw.DimForecastFeature VALUES
    -- Solar
    (1,  'GlobalHorizontalIrradiance',  'Solar',      'Weather',      'GHI in W/m² — primary solar generation driver', 1),
    (2,  'CloudConditions',             'Solar',      'Weather',      'Cloud cover index 0–1 from satellite or on-site sensor', 1),
    (3,  'AmbientTemperature',          'Solar',      'Weather',      'Affects panel output via temperature derating coefficient', 1),
    (4,  'PanelTemperature',            'Solar',      'Weather',      'Module temperature — direct efficiency impact', 1),
    (5,  'InverterAvailability',        'Solar',      'Operational',  'Fraction of inverters online; drives effective DC-AC capacity', 1),
    (6,  'CurtailmentFactor',           'Solar',      'Operational',  'Grid curtailment instruction (0=full curtail, 1=none)', 1),
    -- Wind
    (7,  'WindSpeedMs',                 'Wind',       'Weather',      'Hub-height wind speed in m/s — P-curve primary driver', 1),
    (8,  'WindDirection',               'Wind',       'Weather',      'Wind direction — turbine yaw alignment and wake losses', 1),
    (9,  'AirDensity',                  'Wind',       'Weather',      'Affects turbine power output; varies with altitude and temp', 1),
    (10, 'TurbineAvailability',         'Wind',       'Operational',  'Fraction of turbines available; excludes planned maintenance', 1),
    (11, 'WakeLossFactor',              'Wind',       'Operational',  'Estimated wake interaction loss between turbines', 1),
    -- Gas / HFO
    (12, 'DispatchInstruction',         'Gas-HFO',    'Operational',  'MW dispatch order from off-taker or system operator', 1),
    (13, 'AmbientTemperatureDerating',  'Gas-HFO',    'Weather',      'Hot-day capacity reduction due to compressor inlet conditions', 1),
    (14, 'FuelAvailability',            'Gas-HFO',    'Operational',  'Binary or index: gas pressure / HFO stock level adequate', 1),
    (15, 'HeatRate',                    'Gas-HFO',    'Operational',  'BTU/kWh or GJ/MWh — efficiency measure linked to derating', 1),
    (16, 'PlantAvailability',           'Gas-HFO',    'Operational',  'Scheduled and forced outage adjusted capacity fraction', 1),
    -- Geothermal
    (17, 'SteamPressureBar',            'Geothermal', 'Operational',  'Wellhead steam pressure — primary geothermal output driver', 1),
    (18, 'SteamFlowTonsPerHour',        'Geothermal', 'Operational',  'Mass flow rate determines turbine shaft power', 1),
    (19, 'WellAvailability',            'Geothermal', 'Operational',  'Fraction of production wells online', 1),
    (20, 'CondenserConditions',         'Geothermal', 'Operational',  'Cooling tower / condenser performance; affects back-pressure', 1),
    -- BESS
    (21, 'StateOfChargePct',            'BESS',       'Operational',  'Battery state of charge 0–100%; constrains charge/discharge', 1),
    (22, 'ChargeDischargeSchedule',     'BESS',       'Operational',  'Planned charge/discharge instruction from grid or market', 1),
    (23, 'RoundTripEfficiency',         'BESS',       'Operational',  'Energy round-trip efficiency; degrades with cycle count', 1),
    (24, 'GridMarketDispatchSignal',    'BESS',       'Commercial',   'Real-time price or dispatch trigger from grid operator', 1),
    -- Shared temporal
    (25, 'HourOfDay',                   'All',        'Temporal',     'Captures diurnal patterns for all technologies', 1),
    (26, 'DayOfWeek',                   'All',        'Temporal',     'Demand and dispatch patterns differ weekday vs weekend', 1),
    (27, 'MonthOfYear',                 'All',        'Temporal',     'Seasonal solar angle, wind regime, hydro seasonality', 1),
    (28, 'PublicHoliday',               'All',        'Temporal',     'Reduced dispatch on public holidays for some PPAs', 1),
    (29, 'Lag1h',                       'All',        'Temporal',     'Previous-hour reading — strong short-horizon predictor', 1),
    (30, 'Lag24h',                      'All',        'Temporal',     'Same hour yesterday — captures diurnal autocorrelation', 1),
    (31, 'Lag168h',                     'All',        'Temporal',     'Same hour last week — captures weekly seasonal profile', 1);
END;
GO

-- ============================================================
-- SECTION 5 — BridgeForecastModelFeature
-- ============================================================
IF OBJECT_ID(N'dw.BridgeForecastModelFeature', N'U') IS NULL
BEGIN
    CREATE TABLE dw.BridgeForecastModelFeature
    (
        BridgeKey           INT NOT NULL PRIMARY KEY,
        ForecastModelKey    INT NOT NULL,
        ForecastFeatureKey  INT NOT NULL,
        FeatureImportance   DECIMAL(9,4) NULL,   -- normalised 0–1 from model output
        CONSTRAINT UQ_BridgeForecastModelFeature UNIQUE (ForecastModelKey, ForecastFeatureKey),
        CONSTRAINT FK_BridgeFMF_Model   FOREIGN KEY (ForecastModelKey)   REFERENCES dw.DimForecastModel(ForecastModelKey),
        CONSTRAINT FK_BridgeFMF_Feature FOREIGN KEY (ForecastFeatureKey) REFERENCES dw.DimForecastFeature(ForecastFeatureKey)
    );

    -- Assign primary features to the three core forecasting models
    INSERT INTO dw.BridgeForecastModelFeature VALUES
    -- Model 1: Weekly Seasonal Profile
    ( 1,1,25,0.35),( 2,1,26,0.30),( 3,1,27,0.20),( 4,1,28,0.10),( 5,1,31,0.05),
    -- Model 2: Robust Dynamic Regression
    ( 6,2, 1,0.30),( 7,2, 7,0.25),( 8,2, 3,0.15),( 9,2,25,0.10),(10,2,16,0.10),
    (11,2,29,0.05),(12,2,30,0.05),
    -- Model 3: Technology-Aware Weather GBM (includes all tech groups)
    (13,3, 1,0.22),(14,3, 5,0.15),(15,3, 6,0.10),(16,3, 7,0.18),(17,3, 9,0.08),
    (18,3,10,0.08),(19,3,12,0.05),(20,3,15,0.05),(21,3,29,0.04),(22,3,30,0.03),
    (23,3,25,0.02);
END;
GO

-- ============================================================
-- SECTION 6 — FactMeterReadingHourly
-- Preserves raw reading; clean reading populated by Silver layer.
-- ============================================================
IF OBJECT_ID(N'dw.FactMeterReadingHourly', N'U') IS NULL
BEGIN
    CREATE TABLE dw.FactMeterReadingHourly
    (
        DateKey             INT             NOT NULL,
        TimeKey             TINYINT         NOT NULL,   -- 0–23 FK to DimTime
        PlantKey            INT             NOT NULL,
        MeterKey            INT             NOT NULL,
        RawEnergyMWh        DECIMAL(18,6)   NULL,       -- As-received from SCADA; never overwritten
        CleanEnergyMWh      DECIMAL(18,6)   NULL,       -- Post imputation / outlier correction
        QualityStatus       NVARCHAR(20)    NOT NULL,   -- GOOD / MISSING / OUTLIER / IMPUTED / SUSPECT
        IsMissing           BIT             NOT NULL CONSTRAINT DF_FMR_IsMissing  DEFAULT(0),
        IsOutlier           BIT             NOT NULL CONSTRAINT DF_FMR_IsOutlier  DEFAULT(0),
        IsImputed           BIT             NOT NULL CONSTRAINT DF_FMR_IsImputed  DEFAULT(0),
        ImputationMethod    NVARCHAR(50)    NULL,       -- ForwardFill / HourlyMedian / PlantDayMedian / NULL
        SourceSystem        NVARCHAR(50)    NULL,       -- SCADA / ERP / Manual
        IsSynthetic         BIT             NOT NULL,
        CONSTRAINT PK_FactMeterReadingHourly PRIMARY KEY (DateKey, TimeKey, PlantKey, MeterKey),
        CONSTRAINT FK_FMR_Date   FOREIGN KEY (DateKey)  REFERENCES dw.DimDate(DateKey),
        CONSTRAINT FK_FMR_Time   FOREIGN KEY (TimeKey)  REFERENCES dw.DimTime(TimeKey),
        CONSTRAINT FK_FMR_Plant  FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
        CONSTRAINT FK_FMR_Meter  FOREIGN KEY (MeterKey) REFERENCES dw.DimMeter(MeterKey),
        CONSTRAINT CK_FMR_Status CHECK (QualityStatus IN ('GOOD','MISSING','OUTLIER','IMPUTED','SUSPECT'))
    );
    CREATE INDEX IX_FMR_Plant_Date ON dw.FactMeterReadingHourly (PlantKey, DateKey);
END;
GO

-- ============================================================
-- SECTION 7 — FactDataQualityEvent
-- Immutable audit log; one row per identified issue.
-- NEVER delete rows from this table — use ResolutionStatus.
-- ============================================================
IF OBJECT_ID(N'dw.FactDataQualityEvent', N'U') IS NULL
BEGIN
    CREATE TABLE dw.FactDataQualityEvent
    (
        EventKey            BIGINT          NOT NULL IDENTITY(1,1) PRIMARY KEY,
        DateKey             INT             NOT NULL,
        TimeKey             TINYINT         NULL,
        PlantKey            INT             NOT NULL,
        MeterKey            INT             NULL,
        EventType           NVARCHAR(50)    NOT NULL,   -- MISSING / OUTLIER / DUPLICATE / FORMAT_ERROR / IMPOSSIBLE_VALUE
        AffectedColumn      NVARCHAR(100)   NOT NULL,
        RawValue            NVARCHAR(200)   NULL,
        CorrectedValue      NVARCHAR(200)   NULL,
        QualityRule         NVARCHAR(300)   NOT NULL,   -- Human-readable rule that triggered event
        ResolutionStatus    NVARCHAR(30)    NOT NULL,   -- OPEN / RESOLVED / ACCEPTED / REJECTED
        DetectedByProcess   NVARCHAR(100)   NULL,       -- Silver_Transform / ManualReview / etc.
        DetectedAt          DATETIME2(0)    NOT NULL CONSTRAINT DF_DQE_Detected DEFAULT (GETDATE()),
        IsSynthetic         BIT             NOT NULL,
        CONSTRAINT FK_DQE_Date  FOREIGN KEY (DateKey)  REFERENCES dw.DimDate(DateKey),
        CONSTRAINT FK_DQE_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
        CONSTRAINT CK_DQE_EventType CHECK (EventType IN (
            'MISSING','OUTLIER','DUPLICATE','FORMAT_ERROR','IMPOSSIBLE_VALUE',
            'STALE_SENSOR','FAULT_CODE','MAGNITUDE_ERROR','DATE_LOGIC_ERROR')),
        CONSTRAINT CK_DQE_Resolution CHECK (ResolutionStatus IN ('OPEN','RESOLVED','ACCEPTED','REJECTED'))
    );
    CREATE INDEX IX_DQE_Plant_Date         ON dw.FactDataQualityEvent (PlantKey, DateKey);
    CREATE INDEX IX_DQE_ResolutionStatus   ON dw.FactDataQualityEvent (ResolutionStatus);
    CREATE INDEX IX_DQE_EventType          ON dw.FactDataQualityEvent (EventType);
END;
GO

-- ============================================================
-- SECTION 8 — FactForecastDaily
-- ============================================================
IF OBJECT_ID(N'dw.FactForecastDaily', N'U') IS NULL
BEGIN
    CREATE TABLE dw.FactForecastDaily
    (
        ForecastKey             BIGINT          NOT NULL IDENTITY(1,1) PRIMARY KEY,
        DateKey                 INT             NOT NULL,
        PlantKey                INT             NOT NULL,
        ForecastModelKey        INT             NOT NULL,
        ForecastHorizonDays     TINYINT         NOT NULL,   -- 1 = day-ahead, 7 = week-ahead
        ForecastedEnergyMWh     DECIMAL(18,3)   NOT NULL,
        PredictionLowerMWh      DECIMAL(18,3)   NULL,       -- 10th-percentile bound
        PredictionUpperMWh      DECIMAL(18,3)   NULL,       -- 90th-percentile bound
        GeneratedAt             DATETIME2(0)    NOT NULL CONSTRAINT DF_FFD_Generated DEFAULT (GETDATE()),
        IsSynthetic             BIT             NOT NULL,
        CONSTRAINT UQ_FactForecastDaily UNIQUE (DateKey, PlantKey, ForecastModelKey, ForecastHorizonDays),
        CONSTRAINT FK_FFD_Date   FOREIGN KEY (DateKey)          REFERENCES dw.DimDate(DateKey),
        CONSTRAINT FK_FFD_Plant  FOREIGN KEY (PlantKey)         REFERENCES dw.DimPlant(PlantKey),
        CONSTRAINT FK_FFD_Model  FOREIGN KEY (ForecastModelKey) REFERENCES dw.DimForecastModel(ForecastModelKey)
    );
    CREATE INDEX IX_FFD_Plant_Date ON dw.FactForecastDaily (PlantKey, DateKey);
END;
GO

-- ============================================================
-- SECTION 9 — FactForecastModelValidation
-- Model selection: lowest validation RMSE wins;
-- tie-breaker = lowest absolute total forecast bias.
-- MAPE must not be used as primary metric (unreliable near zero).
-- ============================================================
IF OBJECT_ID(N'dw.FactForecastModelValidation', N'U') IS NULL
BEGIN
    CREATE TABLE dw.FactForecastModelValidation
    (
        ValidationKey           INT             NOT NULL IDENTITY(1,1) PRIMARY KEY,
        ForecastModelKey        INT             NOT NULL,
        PlantKey                INT             NOT NULL,
        ValidationDateKey       INT             NOT NULL,
        MAE                     DECIMAL(18,4)   NOT NULL,
        RMSE                    DECIMAL(18,4)   NOT NULL,   -- PRIMARY selection metric
        MAPE                    DECIMAL(18,4)   NULL,       -- Stored; NOT used for selection on near-zero data
        sMAPE                   DECIMAL(18,4)   NULL,
        RSquared                DECIMAL(9,6)    NULL,
        ActualTotalEnergyMWh    DECIMAL(18,3)   NOT NULL,
        ForecastTotalEnergyMWh  DECIMAL(18,3)   NOT NULL,
        TotalBiasPct            DECIMAL(18,4)   NOT NULL,   -- Tie-breaker: lowest |TotalBiasPct|
        IsSelectedModel         BIT             NOT NULL,
        IsSynthetic             BIT             NOT NULL,
        CONSTRAINT UQ_FactFMV UNIQUE (ForecastModelKey, PlantKey, ValidationDateKey),
        CONSTRAINT FK_FMV_Model FOREIGN KEY (ForecastModelKey) REFERENCES dw.DimForecastModel(ForecastModelKey),
        CONSTRAINT FK_FMV_Plant FOREIGN KEY (PlantKey)         REFERENCES dw.DimPlant(PlantKey),
        CONSTRAINT FK_FMV_Date  FOREIGN KEY (ValidationDateKey)REFERENCES dw.DimDate(DateKey)
    );
    CREATE INDEX IX_FMV_Plant_Model ON dw.FactForecastModelValidation (PlantKey, ForecastModelKey);
END;
GO

-- ============================================================
-- SECTION 10 — FactWeatherNormalisedPerf
-- ============================================================
IF OBJECT_ID(N'dw.FactWeatherNormalisedPerf', N'U') IS NULL
BEGIN
    CREATE TABLE dw.FactWeatherNormalisedPerf
    (
        DateKey                         INT             NOT NULL,
        PlantKey                        INT             NOT NULL,
        ActualGenerationMWh             DECIMAL(18,3)   NOT NULL,
        WeatherNormalisedGenerationMWh  DECIMAL(18,3)   NOT NULL,
        VarianceMWh                     DECIMAL(18,3)   NOT NULL,
        VariancePct                     DECIMAL(9,3)    NOT NULL,
        ResidualZScore                  DECIMAL(9,4)    NULL,
        IsExceptionDay                  BIT             NOT NULL,   -- |Z-score| > 2
        PrimaryWeatherDriver            NVARCHAR(100)   NULL,       -- GHI / WindSpeed / SteamPressure
        WeatherDriverValue              DECIMAL(18,4)   NULL,
        IsSynthetic                     BIT             NOT NULL,
        CONSTRAINT PK_FactWNP PRIMARY KEY (DateKey, PlantKey),
        CONSTRAINT FK_WNP_Date  FOREIGN KEY (DateKey)  REFERENCES dw.DimDate(DateKey),
        CONSTRAINT FK_WNP_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
    );
END;
GO

-- ============================================================
-- SECTION 11 — BI Views
-- ============================================================
GO
CREATE OR ALTER VIEW bi.vw_MeterDataQuality AS
SELECT
    d.CalendarYear,
    d.CalendarMonthName,
    d.YearMonth,
    p.PlantName,
    p.PrimaryTechnologyName,
    p.ProjectStatus,
    m.MeterCode,
    m.MeterType,
    COUNT(*)                                                    AS TotalIntervals,
    SUM(CAST(f.IsMissing   AS INT))                            AS MissingIntervals,
    SUM(CAST(f.IsOutlier   AS INT))                            AS OutlierIntervals,
    SUM(CAST(f.IsImputed   AS INT))                            AS ImputedIntervals,
    SUM(CASE WHEN f.QualityStatus = 'GOOD' THEN 1 ELSE 0 END) AS GoodIntervals,
    CAST(100.0 * SUM(CASE WHEN f.QualityStatus = 'GOOD' THEN 1 ELSE 0 END)
         / NULLIF(COUNT(*),0) AS DECIMAL(9,2))                 AS DataCompletenessPct,
    CAST(100.0 * SUM(CAST(f.IsImputed AS INT))
         / NULLIF(COUNT(*),0) AS DECIMAL(9,2))                 AS ImputedPct
FROM dw.FactMeterReadingHourly f
JOIN dw.DimDate   d ON f.DateKey  = d.DateKey
JOIN dw.DimPlant  p ON f.PlantKey = p.PlantKey
JOIN dw.DimMeter  m ON f.MeterKey = m.MeterKey
GROUP BY d.CalendarYear, d.CalendarMonthName, d.YearMonth,
         p.PlantName, p.PrimaryTechnologyName, p.ProjectStatus,
         m.MeterCode, m.MeterType;
GO

CREATE OR ALTER VIEW bi.vw_ForecastVsActual AS
SELECT
    d.CalendarYear,
    d.YearMonth,
    d.FullDate,
    p.PlantName,
    p.PrimaryTechnologyName,
    fm.ModelName,
    fm.ModelFamily,
    fm.IsSelectedModel,
    ff.ForecastHorizonDays,
    ops.NetGenerationMWh                            AS ActualGenerationMWh,
    ff.ForecastedEnergyMWh,
    ff.PredictionLowerMWh,
    ff.PredictionUpperMWh,
    ops.NetGenerationMWh - ff.ForecastedEnergyMWh  AS ForecastErrorMWh,
    CASE WHEN ops.NetGenerationMWh > 0
         THEN CAST(100.0 * (ops.NetGenerationMWh - ff.ForecastedEnergyMWh)
                   / ops.NetGenerationMWh AS DECIMAL(9,3))
         ELSE NULL
    END                                             AS ForecastErrorPct
FROM dw.FactForecastDaily ff
JOIN dw.DimDate            d   ON ff.DateKey          = d.DateKey
JOIN dw.DimPlant           p   ON ff.PlantKey         = p.PlantKey
JOIN dw.DimForecastModel   fm  ON ff.ForecastModelKey = fm.ForecastModelKey
LEFT JOIN dw.FactPlantOperationsDaily ops
    ON ff.DateKey = ops.DateKey AND ff.PlantKey = ops.PlantKey;
GO

CREATE OR ALTER VIEW bi.vw_ModelScorecard AS
SELECT
    p.PlantName,
    p.PrimaryTechnologyName,
    fm.ModelName,
    fm.ModelFamily,
    fm.ModelVersion,
    fm.ModelStatus,
    fm.IsSelectedModel,
    d.YearMonth                         AS ValidationPeriod,
    v.MAE,
    v.RMSE,
    v.MAPE,
    v.sMAPE,
    v.RSquared,
    v.ActualTotalEnergyMWh,
    v.ForecastTotalEnergyMWh,
    v.TotalBiasPct,
    v.IsSelectedModel                   AS SelectedForThisPlant,
    fm.SelectionCriteria,
    fm.Notes
FROM dw.FactForecastModelValidation v
JOIN dw.DimForecastModel fm ON v.ForecastModelKey   = fm.ForecastModelKey
JOIN dw.DimPlant          p ON v.PlantKey            = p.PlantKey
JOIN dw.DimDate           d ON v.ValidationDateKey   = d.DateKey;
GO

CREATE OR ALTER VIEW bi.vw_WeatherNormalisedPerf AS
SELECT
    d.CalendarYear,
    d.YearMonth,
    d.FullDate,
    p.PlantName,
    p.PrimaryTechnologyName,
    g.CountryName,
    g.RegionName,
    w.ActualGenerationMWh,
    w.WeatherNormalisedGenerationMWh,
    w.VarianceMWh,
    w.VariancePct,
    w.ResidualZScore,
    w.IsExceptionDay,
    w.PrimaryWeatherDriver,
    w.WeatherDriverValue
FROM dw.FactWeatherNormalisedPerf w
JOIN dw.DimDate      d ON w.DateKey  = d.DateKey
JOIN dw.DimPlant     p ON w.PlantKey = p.PlantKey
JOIN dw.DimGeography g ON p.GeographyKey = g.GeographyKey;
GO

CREATE OR ALTER VIEW bi.vw_DataQualityEvents AS
SELECT
    d.CalendarYear,
    d.YearMonth,
    d.FullDate,
    p.PlantName,
    p.PrimaryTechnologyName,
    m.MeterCode,
    e.EventType,
    e.AffectedColumn,
    e.RawValue,
    e.CorrectedValue,
    e.QualityRule,
    e.ResolutionStatus,
    e.DetectedByProcess,
    e.DetectedAt,
    e.IsSynthetic
FROM dw.FactDataQualityEvent e
JOIN dw.DimDate  d ON e.DateKey  = d.DateKey
JOIN dw.DimPlant p ON e.PlantKey = p.PlantKey
LEFT JOIN dw.DimMeter m ON e.MeterKey = m.MeterKey;
GO

CREATE OR ALTER VIEW bi.vw_ForecastModelRegistry AS
SELECT
    fm.ForecastModelKey,
    fm.ModelName,
    fm.ModelFamily,
    fm.ModelVersion,
    fm.TrainingPeriodStart,
    fm.TrainingPeriodEnd,
    fm.ValidationPeriodStart,
    fm.ValidationPeriodEnd,
    fm.RetrainingFrequency,
    fm.IsRecursiveForecast,
    fm.ModelStatus,
    fm.IsSelectedModel,
    fm.SelectionCriteria,
    fm.PrimaryFeatures,
    fm.Notes,
    COUNT(ff.ForecastFeatureKey)    AS FeatureCount,
    AVG(b.FeatureImportance)        AS AvgFeatureImportance
FROM dw.DimForecastModel fm
LEFT JOIN dw.BridgeForecastModelFeature b  ON fm.ForecastModelKey  = b.ForecastModelKey
LEFT JOIN dw.DimForecastFeature         ff ON b.ForecastFeatureKey = ff.ForecastFeatureKey
GROUP BY
    fm.ForecastModelKey, fm.ModelName, fm.ModelFamily, fm.ModelVersion,
    fm.TrainingPeriodStart, fm.TrainingPeriodEnd,
    fm.ValidationPeriodStart, fm.ValidationPeriodEnd,
    fm.RetrainingFrequency, fm.IsRecursiveForecast,
    fm.ModelStatus, fm.IsSelectedModel, fm.SelectionCriteria,
    fm.PrimaryFeatures, fm.Notes;
GO

PRINT 'Baobab Power V2 Upgrade complete.';
PRINT '  New tables: DimTime, DimMeter, DimForecastModel, DimForecastFeature,';
PRINT '              BridgeForecastModelFeature, FactMeterReadingHourly,';
PRINT '              FactDataQualityEvent, FactForecastDaily,';
PRINT '              FactForecastModelValidation, FactWeatherNormalisedPerf';
PRINT '  New views:  bi.vw_MeterDataQuality, bi.vw_ForecastVsActual,';
PRINT '              bi.vw_ModelScorecard, bi.vw_WeatherNormalisedPerf,';
PRINT '              bi.vw_DataQualityEvents, bi.vw_ForecastModelRegistry';
GO
