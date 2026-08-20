/*
Aquila Energy Portfolio Data Warehouse
SQL Server 2019+ / Azure SQL compatible

IMPORTANT:
1. Static plant, technology, geography, organisation and agreement data is sourced from the
   uploaded Aquila brochure snapshot.
2. Operational, financial, outage, maintenance, construction and HSE fact CSVs are synthetic.
3. Verify current project status, agreement dates, tariffs and ownership percentages before production use.
*/
IF DB_ID(N'AquilaEnergyDW') IS NULL
BEGIN
    CREATE DATABASE AquilaEnergyDW;
END;
GO

USE AquilaEnergyDW;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'dw') EXEC(N'CREATE SCHEMA dw');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'bi') EXEC(N'CREATE SCHEMA bi');
GO

DROP VIEW IF EXISTS bi.vw_PortfolioOverview;
DROP VIEW IF EXISTS bi.vw_DailyPlantPerformance;
DROP VIEW IF EXISTS bi.vw_MonthlyCommercialPerformance;
DROP VIEW IF EXISTS bi.vw_MaintenanceReliability;
GO

DROP TABLE IF EXISTS dw.FactHSEIncident;
DROP TABLE IF EXISTS dw.FactConstructionProgressMonthly;
DROP TABLE IF EXISTS dw.FactMaintenanceWorkOrder;
DROP TABLE IF EXISTS dw.FactOutage;
DROP TABLE IF EXISTS dw.FactEnergySalesMonthly;
DROP TABLE IF EXISTS dw.FactFXRateMonthly;
DROP TABLE IF EXISTS dw.FactBatteryOperationDaily;
DROP TABLE IF EXISTS dw.FactPlantOperationsDaily;
DROP TABLE IF EXISTS dw.BridgePlantOrganisation;
DROP TABLE IF EXISTS dw.BridgePlantTechnology;
DROP TABLE IF EXISTS dw.DimAsset;
DROP TABLE IF EXISTS dw.DimAgreement;
DROP TABLE IF EXISTS dw.DimPlant;
DROP TABLE IF EXISTS dw.DimOrganisation;
DROP TABLE IF EXISTS dw.DimTechnology;
DROP TABLE IF EXISTS dw.DimGeography;
DROP TABLE IF EXISTS dw.DimDate;
GO

CREATE TABLE dw.DimDate
(
    DateKey                 INT             NOT NULL PRIMARY KEY,
    FullDate                DATE            NOT NULL UNIQUE,
    CalendarYear            SMALLINT        NOT NULL,
    CalendarQuarter         TINYINT         NOT NULL,
    CalendarMonthNumber     TINYINT         NOT NULL,
    CalendarMonthName       NVARCHAR(20)    NOT NULL,
    YearMonth               CHAR(7)         NOT NULL,
    ISOWeekNumber           TINYINT         NOT NULL,
    DayOfMonth              TINYINT         NOT NULL,
    DayOfWeekNumber         TINYINT         NOT NULL,
    DayOfWeekName           NVARCHAR(20)    NOT NULL,
    IsWeekend               BIT             NOT NULL,
    FinancialYearStartYear  SMALLINT        NOT NULL,
    FinancialYearLabel      CHAR(9)         NOT NULL
);
GO

CREATE TABLE dw.DimGeography
(
    GeographyKey    INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CountryName     NVARCHAR(100) NOT NULL,
    ISO3Code        CHAR(3) NULL,
    RegionName      NVARCHAR(100) NOT NULL,
    CONSTRAINT UQ_DimGeography UNIQUE (CountryName)
);
GO

CREATE TABLE dw.DimTechnology
(
    TechnologyKey                       INT NOT NULL PRIMARY KEY,
    TechnologyName                      NVARCHAR(100) NOT NULL,
    TechnologyGroup                     NVARCHAR(50) NOT NULL,
    FuelType                            NVARCHAR(50) NULL,
    IndicativeEmissionsFactorTCO2PerMWh DECIMAL(12,6) NULL,
    CONSTRAINT UQ_DimTechnology UNIQUE (TechnologyName)
);
GO

CREATE TABLE dw.DimOrganisation
(
    OrganisationKey     INT NOT NULL PRIMARY KEY,
    OrganisationName    NVARCHAR(200) NOT NULL,
    OrganisationType    NVARCHAR(100) NOT NULL,
    CONSTRAINT UQ_DimOrganisation UNIQUE (OrganisationName)
);
GO

CREATE TABLE dw.DimPlant
(
    PlantKey                        INT NOT NULL PRIMARY KEY,
    PlantCode                       NVARCHAR(30) NOT NULL,
    PlantName                       NVARCHAR(200) NOT NULL,
    GeographyKey                    INT NOT NULL,
    City                            NVARCHAR(100) NULL,
    Province                        NVARCHAR(100) NULL,
    ProjectStatus                   NVARCHAR(50) NOT NULL,
    PrimaryTechnologyName           NVARCHAR(100) NOT NULL,
    NameplateCapacity               DECIMAL(14,3) NOT NULL,
    CapacityUnit                    NVARCHAR(10) NOT NULL,
    StorageCapacityMWh              DECIMAL(14,3) NULL,
    BrochureAnnualGenerationGWh     DECIMAL(14,3) NULL,
    BrochureHomesEquivalent         BIGINT NULL,
    BrochureCO2AvoidedTonnes        DECIMAL(18,3) NULL,
    SourceNotes                     NVARCHAR(1000) NULL,
    IsActive                        BIT NOT NULL CONSTRAINT DF_DimPlant_IsActive DEFAULT (1),
    CONSTRAINT UQ_DimPlant_Code UNIQUE (PlantCode),
    CONSTRAINT UQ_DimPlant_Name UNIQUE (PlantName),
    CONSTRAINT FK_DimPlant_Geography FOREIGN KEY (GeographyKey) REFERENCES dw.DimGeography(GeographyKey)
);
GO

CREATE TABLE dw.DimAgreement
(
    AgreementKey                   INT NOT NULL PRIMARY KEY,
    PlantKey                       INT NOT NULL,
    CounterpartyOrganisationKey    INT NULL,
    AgreementType                  NVARCHAR(100) NOT NULL,
    TermYears                      SMALLINT NULL,
    StartDate                      DATE NULL,
    EndDate                        DATE NULL,
    AgreementStatus                NVARCHAR(50) NOT NULL,
    IsBrochureSourced              BIT NOT NULL,
    CONSTRAINT FK_DimAgreement_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
    CONSTRAINT FK_DimAgreement_Organisation FOREIGN KEY (CounterpartyOrganisationKey) REFERENCES dw.DimOrganisation(OrganisationKey)
);
GO

CREATE TABLE dw.DimAsset
(
    AssetKey        INT NOT NULL PRIMARY KEY,
    PlantKey        INT NOT NULL,
    AssetCode       NVARCHAR(50) NOT NULL,
    AssetName       NVARCHAR(200) NOT NULL,
    AssetType       NVARCHAR(100) NOT NULL,
    AssetStatus     NVARCHAR(50) NOT NULL,
    CONSTRAINT UQ_DimAsset_Code UNIQUE (AssetCode),
    CONSTRAINT FK_DimAsset_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

CREATE TABLE dw.BridgePlantTechnology
(
    PlantTechnologyKey INT NOT NULL PRIMARY KEY,
    PlantKey           INT NOT NULL,
    TechnologyKey      INT NOT NULL,
    InstalledCapacity  DECIMAL(14,3) NOT NULL,
    CapacityUnit       NVARCHAR(10) NOT NULL,
    IsPrimary          BIT NOT NULL,
    CONSTRAINT FK_BridgePlantTechnology_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
    CONSTRAINT FK_BridgePlantTechnology_Technology FOREIGN KEY (TechnologyKey) REFERENCES dw.DimTechnology(TechnologyKey),
    CONSTRAINT UQ_BridgePlantTechnology UNIQUE (PlantKey, TechnologyKey, CapacityUnit)
);
GO

CREATE TABLE dw.BridgePlantOrganisation
(
    PlantOrganisationKey   INT NOT NULL PRIMARY KEY,
    PlantKey               INT NOT NULL,
    OrganisationKey        INT NOT NULL,
    RoleType                NVARCHAR(100) NOT NULL,
    OwnershipPercent        DECIMAL(9,4) NULL,
    Notes                   NVARCHAR(500) NULL,
    CONSTRAINT FK_BridgePlantOrganisation_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
    CONSTRAINT FK_BridgePlantOrganisation_Organisation FOREIGN KEY (OrganisationKey) REFERENCES dw.DimOrganisation(OrganisationKey)
);
GO

CREATE TABLE dw.FactPlantOperationsDaily
(
    DateKey                     INT NOT NULL,
    PlantKey                    INT NOT NULL,
    GrossGenerationMWh          DECIMAL(18,3) NOT NULL,
    NetGenerationMWh            DECIMAL(18,3) NOT NULL,
    EnergyExportedMWh           DECIMAL(18,3) NOT NULL,
    AvailabilityPct             DECIMAL(9,3) NOT NULL,
    CapacityFactorPct           DECIMAL(9,3) NOT NULL,
    CurtailmentPct              DECIMAL(9,3) NOT NULL,
    PlannedDowntimeHours        DECIMAL(9,3) NOT NULL,
    ForcedDowntimeHours         DECIMAL(9,3) NOT NULL,
    Scope1EmissionsTonnesCO2e   DECIMAL(18,3) NOT NULL,
    CO2AvoidedTonnes            DECIMAL(18,3) NOT NULL,
    IsSynthetic                 BIT NOT NULL,
    CONSTRAINT PK_FactPlantOperationsDaily PRIMARY KEY (DateKey, PlantKey),
    CONSTRAINT FK_FactPlantOperationsDaily_Date FOREIGN KEY (DateKey) REFERENCES dw.DimDate(DateKey),
    CONSTRAINT FK_FactPlantOperationsDaily_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

CREATE TABLE dw.FactBatteryOperationDaily
(
    DateKey                     INT NOT NULL,
    PlantKey                    INT NOT NULL,
    EnergyChargedMWh            DECIMAL(18,3) NOT NULL,
    EnergyDischargedMWh         DECIMAL(18,3) NOT NULL,
    RoundTripEfficiencyPct      DECIMAL(9,3) NOT NULL,
    MinimumStateOfChargePct     DECIMAL(9,3) NOT NULL,
    MaximumStateOfChargePct     DECIMAL(9,3) NOT NULL,
    IsSynthetic                 BIT NOT NULL,
    CONSTRAINT PK_FactBatteryOperationDaily PRIMARY KEY (DateKey, PlantKey),
    CONSTRAINT FK_FactBatteryOperationDaily_Date FOREIGN KEY (DateKey) REFERENCES dw.DimDate(DateKey),
    CONSTRAINT FK_FactBatteryOperationDaily_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

CREATE TABLE dw.FactFXRateMonthly
(
    MonthDateKey    INT NOT NULL,
    CurrencyCode    CHAR(3) NOT NULL,
    CurrencyName    NVARCHAR(100) NOT NULL,
    RateToZAR       DECIMAL(18,6) NOT NULL,
    IsSynthetic     BIT NOT NULL,
    CONSTRAINT PK_FactFXRateMonthly PRIMARY KEY (MonthDateKey, CurrencyCode),
    CONSTRAINT FK_FactFXRateMonthly_Date FOREIGN KEY (MonthDateKey) REFERENCES dw.DimDate(DateKey)
);
GO

CREATE TABLE dw.FactEnergySalesMonthly
(
    MonthDateKey                INT NOT NULL,
    PlantKey                    INT NOT NULL,
    CurrencyCode                CHAR(3) NOT NULL,
    EnergySoldMWh               DECIMAL(18,3) NOT NULL,
    AverageTariffPerKWhLocal    DECIMAL(18,6) NOT NULL,
    RevenueLocalCurrency        DECIMAL(20,2) NOT NULL,
    FXRateToZAR                 DECIMAL(18,6) NOT NULL,
    RevenueZAR                  DECIMAL(20,2) NOT NULL,
    SettlementCollectionPct     DECIMAL(9,3) NOT NULL,
    IsSynthetic                 BIT NOT NULL,
    CONSTRAINT PK_FactEnergySalesMonthly PRIMARY KEY (MonthDateKey, PlantKey),
    CONSTRAINT FK_FactEnergySalesMonthly_Date FOREIGN KEY (MonthDateKey) REFERENCES dw.DimDate(DateKey),
    CONSTRAINT FK_FactEnergySalesMonthly_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

CREATE TABLE dw.FactOutage
(
    OutageKey                   BIGINT NOT NULL PRIMARY KEY,
    PlantKey                    INT NOT NULL,
    AssetKey                    INT NULL,
    OutageStartDateTime         DATETIME2(0) NOT NULL,
    OutageEndDateTime           DATETIME2(0) NOT NULL,
    OutageType                  NVARCHAR(30) NOT NULL,
    DurationHours               DECIMAL(12,3) NOT NULL,
    EstimatedEnergyLostMWh      DECIMAL(18,3) NOT NULL,
    RootCauseCategory           NVARCHAR(200) NULL,
    IsSynthetic                 BIT NOT NULL,
    CONSTRAINT FK_FactOutage_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
    CONSTRAINT FK_FactOutage_Asset FOREIGN KEY (AssetKey) REFERENCES dw.DimAsset(AssetKey),
    CONSTRAINT CK_FactOutage_Dates CHECK (OutageEndDateTime >= OutageStartDateTime)
);
GO

CREATE TABLE dw.FactMaintenanceWorkOrder
(
    WorkOrderKey               BIGINT NOT NULL PRIMARY KEY,
    PlantKey                  INT NOT NULL,
    AssetKey                  INT NULL,
    OpenedDate                DATE NOT NULL,
    ClosedDate                DATE NULL,
    WorkOrderType             NVARCHAR(50) NOT NULL,
    Priority                  NVARCHAR(20) NOT NULL,
    WorkOrderStatus           NVARCHAR(30) NOT NULL,
    LabourHours               DECIMAL(12,2) NOT NULL,
    MaterialCostZAR           DECIMAL(18,2) NOT NULL,
    LabourCostZAR             DECIMAL(18,2) NOT NULL,
    TotalMaintenanceCostZAR   DECIMAL(18,2) NOT NULL,
    IsSynthetic               BIT NOT NULL,
    CONSTRAINT FK_FactMaintenanceWorkOrder_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey),
    CONSTRAINT FK_FactMaintenanceWorkOrder_Asset FOREIGN KEY (AssetKey) REFERENCES dw.DimAsset(AssetKey),
    CONSTRAINT CK_FactMaintenanceWorkOrder_Dates CHECK (ClosedDate IS NULL OR ClosedDate >= OpenedDate)
);
GO

CREATE TABLE dw.FactConstructionProgressMonthly
(
    MonthDateKey          INT NOT NULL,
    PlantKey              INT NOT NULL,
    PlannedProgressPct    DECIMAL(9,2) NOT NULL,
    ActualProgressPct     DECIMAL(9,2) NOT NULL,
    ScheduleVariancePct   DECIMAL(9,2) NOT NULL,
    ApprovedBudgetZAR     DECIMAL(20,2) NOT NULL,
    ActualCostToDateZAR   DECIMAL(20,2) NOT NULL,
    CostVarianceZAR       DECIMAL(20,2) NOT NULL,
    IsSynthetic           BIT NOT NULL,
    CONSTRAINT PK_FactConstructionProgressMonthly PRIMARY KEY (MonthDateKey, PlantKey),
    CONSTRAINT FK_FactConstructionProgressMonthly_Date FOREIGN KEY (MonthDateKey) REFERENCES dw.DimDate(DateKey),
    CONSTRAINT FK_FactConstructionProgressMonthly_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

CREATE TABLE dw.FactHSEIncident
(
    IncidentKey             BIGINT NOT NULL PRIMARY KEY,
    DateKey                 INT NOT NULL,
    PlantKey                INT NOT NULL,
    IncidentType            NVARCHAR(100) NOT NULL,
    Severity                NVARCHAR(20) NOT NULL,
    LostWorkDays            INT NOT NULL,
    InvestigationStatus     NVARCHAR(30) NOT NULL,
    IsSynthetic             BIT NOT NULL,
    CONSTRAINT FK_FactHSEIncident_Date FOREIGN KEY (DateKey) REFERENCES dw.DimDate(DateKey),
    CONSTRAINT FK_FactHSEIncident_Plant FOREIGN KEY (PlantKey) REFERENCES dw.DimPlant(PlantKey)
);
GO

DECLARE @StartDate DATE = '2020-01-01';
DECLARE @EndDate   DATE = '2035-12-31';

;WITH DateSeries AS
(
    SELECT @StartDate AS FullDate
    UNION ALL
    SELECT DATEADD(DAY, 1, FullDate)
    FROM DateSeries
    WHERE FullDate < @EndDate
)
INSERT INTO dw.DimDate
(
    DateKey, FullDate, CalendarYear, CalendarQuarter, CalendarMonthNumber,
    CalendarMonthName, YearMonth, ISOWeekNumber, DayOfMonth, DayOfWeekNumber,
    DayOfWeekName, IsWeekend, FinancialYearStartYear, FinancialYearLabel
)
SELECT
    CONVERT(INT, CONVERT(CHAR(8), FullDate, 112)) AS DateKey,
    FullDate,
    YEAR(FullDate),
    DATEPART(QUARTER, FullDate),
    MONTH(FullDate),
    DATENAME(MONTH, FullDate),
    CONVERT(CHAR(7), FullDate, 126),
    DATEPART(ISO_WEEK, FullDate),
    DAY(FullDate),
    DATEPART(WEEKDAY, FullDate),
    DATENAME(WEEKDAY, FullDate),
    CASE WHEN DATENAME(WEEKDAY, FullDate) IN ('Saturday','Sunday') THEN 1 ELSE 0 END,
    CASE WHEN MONTH(FullDate) >= 4 THEN YEAR(FullDate) ELSE YEAR(FullDate)-1 END,
    CONCAT(
        CASE WHEN MONTH(FullDate) >= 4 THEN YEAR(FullDate) ELSE YEAR(FullDate)-1 END,
        '/',
        RIGHT(CONVERT(VARCHAR(4), CASE WHEN MONTH(FullDate) >= 4 THEN YEAR(FullDate)+1 ELSE YEAR(FullDate) END), 2)
    )
FROM DateSeries
OPTION (MAXRECURSION 0);
GO
SET IDENTITY_INSERT dw.DimGeography ON;
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (1, N'Kenya', N'KEN', N'East Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (2, N'Tanzania', N'TZA', N'East Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (3, N'Egypt', N'EGY', N'Northern Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (4, N'Mozambique', N'MOZ', N'Southern Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (5, N'South Africa', N'ZAF', N'Southern Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (6, N'Cameroon', N'CMR', N'West Africa');
INSERT INTO dw.DimGeography (GeographyKey, CountryName, ISO3Code, RegionName) VALUES (7, N'Côte d’Ivoire', N'CIV', N'West Africa');
SET IDENTITY_INSERT dw.DimGeography OFF;
GO

INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (1, N'Solar PV', N'Renewable', N'Solar', 0.0);
INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (2, N'Wind', N'Renewable', N'Wind', 0.0);
INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (3, N'Natural Gas', N'Thermal', N'Gas', 0.4);
INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (4, N'Heavy Fuel Oil', N'Thermal', N'HFO', 0.7);
INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (5, N'Battery Storage', N'Storage', N'BESS', 0.0);
INSERT INTO dw.DimTechnology (TechnologyKey, TechnologyName, TechnologyGroup, FuelType, IndicativeEmissionsFactorTCO2PerMWh) VALUES (6, N'Geothermal', N'Renewable', N'Geothermal', 0.05);
GO

INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (1, N'Aquila', N'Developer / Owner / Operator');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (2, N'British International Investment (BII)', N'Shareholder');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (3, N'Norfund', N'Shareholder');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (4, N'Eskom', N'Off-taker / Utility');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (5, N'Egyptian Electricity and Transmission Company (EETC)', N'Off-taker / Utility');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (6, N'Government of Côte d’Ivoire', N'Government / Concession Counterparty');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (7, N'ENEO', N'Off-taker / Utility');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (8, N'Government of Cameroon', N'Government / Co-owner');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (9, N'Cameroon National Grid', N'Off-taker / Grid');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (10, N'Kenya Power', N'Off-taker / Utility');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (11, N'EDM', N'Off-taker / Utility');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (12, N'Tanzania National Grid', N'Off-taker / Grid');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (13, N'Al Tawakol GILA', N'Co-shareholder / O&M Partner');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (14, N'Kenya National Grid', N'Off-taker / Grid');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (15, N'Geothermal Development Company (GDC)', N'Steam Supplier');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (16, N'Toyota Tsusho Corporation', N'EPC Contractor');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (17, N'African Development Bank', N'Lender');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (18, N'Trade and Development Bank', N'Lender');
INSERT INTO dw.DimOrganisation (OrganisationKey, OrganisationName, OrganisationType) VALUES (19, N'Finnfund', N'Lender');
GO

INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (1,N'ARC',N'Marsa Alam Solar',3,N'Aswan',NULL,N'Operating',N'Solar PV',66,N'MWp',NULL,NULL,NULL,NULL,N'Remote monitoring from Cape Town; asset management and O&M oversight.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (2,N'ARIES',N'Orange Valley Solar',5,N'Kenhardt',N'Northern Cape',N'Operating',N'Solar PV',11,N'MWp',NULL,21.0,6300,NULL,N'Aquila is majority shareholder and responsible for asset management.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (3,N'AZITO',N'Ebrie Lagoon Power',7,N'Abidjan',NULL,N'Operating',N'Natural Gas',713,N'MW',NULL,NULL,NULL,NULL,N'Natural gas supplied from offshore gas fields; Aquila majority owner.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (4,N'BOSHOF',N'Free State Sun Park',5,N'Boshof',N'Free State',N'Operating',N'Solar PV',66,N'MWp',NULL,130.0,38900,NULL,N'Asset management, operations and maintenance.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (5,N'CUAMBA',N'Niassa Solar Storage',4,N'Cuamba',NULL,N'Operating',N'Solar PV + BESS',19,N'MWp',7.0,NULL,21800,172000.0,N'First IPP in Mozambique to integrate utility-scale storage.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (6,N'DEAAR',N'Hantam Solar Power',5,N'De Aar',N'Northern Cape',N'Operating',N'Solar PV',50,N'MWp',NULL,93.0,28000,NULL,N'Asset management, operations and maintenance.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (7,N'DIBAMBA',N'Wouri Estuary Power',6,N'Douala',NULL,N'Operating',N'Heavy Fuel Oil',88,N'MW',NULL,NULL,NULL,NULL,N'Government of Cameroon holds remaining shares.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (8,N'DROOG',N'Diamond Coast Solar',5,N'Kimberley',N'Northern Cape',N'Operating',N'Solar PV',50,N'MWp',NULL,90.0,27000,NULL,N'Asset management and maintenance.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (9,N'JBAY',N'Cape St Francis Wind Farm',5,N'Jeffreys Bay',N'Eastern Cape',N'Operating',N'Wind',138,N'MW',NULL,448.0,114100,NULL,N'60 turbines at 2.3 MW each.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (10,N'KLIP',N'Overberg Ridge Wind Farm',5,N'Caledon',N'Western Cape',N'Operating',N'Wind',27,N'MW',NULL,86.0,25600,NULL,N'9 turbines at 3 MW each.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (11,N'KONK',N'Bushmanland Solar Power',5,N'Pofadder',N'Northern Cape',N'Operating',N'Solar PV',11,N'MWp',NULL,21.0,6300,NULL,N'Asset management.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (12,N'KRIBI',N'Sanaga Delta Power',6,N'Kribi',NULL,N'Operating',N'Natural Gas',216,N'MW',NULL,NULL,NULL,NULL,N'Natural gas from the offshore Sanaga South gas field.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (13,N'MALINDI',N'Watamu Coast Solar',1,N'Malindi',NULL,N'Operating',N'Solar PV',52,N'MWp',NULL,NULL,NULL,NULL,N'Utility-scale solar plant in Kenya''s coastal area.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (14,N'MOCUBA',N'Zambezia Sun Fields',4,N'Mocuba',N'Zambezia',N'Operating',N'Solar PV',41,N'MWp',NULL,NULL,NULL,NULL,N'Construction completed in August 2019.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (15,N'SONGAS',N'Rufiji Gas Power',2,N'Dar es Salaam',NULL,N'Operating',N'Natural Gas',190,N'MW',NULL,NULL,NULL,NULL,N'Includes gas processing and a 225 km pipeline.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (16,N'SOUTPAN',N'Limpopo Valley Solar',5,N'Vivo',N'Limpopo',N'Operating',N'Solar PV',31,N'MWp',NULL,60.0,17800,NULL,N'Brochure text appears to contain a unit typo (''60 Wh''); model uses 60 GWh.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (17,N'WINNERGY',N'Nubian Sands Solar',3,N'Aswan',NULL,N'Operating',N'Solar PV',25,N'MWp',NULL,NULL,NULL,NULL,N'Co-shareholder Al Tawakol GILA; remote monitoring from Cape Town.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (18,N'CTT',N'Inhambane Gas Power',4,N'Temane',NULL,N'In Construction',N'Natural Gas',450,N'MW',NULL,NULL,1500000,NULL,N'Brochure expected first power in 2024; status is a brochure snapshot and must be verified.',1);
INSERT INTO dw.DimPlant (PlantKey,PlantCode,PlantName,GeographyKey,City,Province,ProjectStatus,PrimaryTechnologyName,NameplateCapacity,CapacityUnit,StorageCapacityMWh,BrochureAnnualGenerationGWh,BrochureHomesEquivalent,BrochureCO2AvoidedTonnes,SourceNotes,IsActive) VALUES (19,N'MENENGAI',N'Nakuru Rift Geothermal',1,N'Nakuru County',NULL,N'In Construction',N'Geothermal',35,N'MW',NULL,NULL,NULL,NULL,N'Steam supplied by GDC; Toyota Tsusho is EPC contractor; brochure expected operations in 2025.',1);
GO

INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (1,1,5,N'Power Purchase Agreement',25,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (2,2,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (3,3,6,N'Concession Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (4,4,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (5,6,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (6,7,7,N'Tolling Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (7,8,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (8,11,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (9,12,9,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (10,13,10,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (11,14,11,N'Power Purchase Agreement',25,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (12,15,12,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (13,16,4,N'Power Purchase Agreement',20,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (14,17,5,N'Power Purchase Agreement',25,NULL,NULL,N'Active/Unknown',1);
INSERT INTO dw.DimAgreement (AgreementKey,PlantKey,CounterpartyOrganisationKey,AgreementType,TermYears,StartDate,EndDate,AgreementStatus,IsBrochureSourced) VALUES (15,18,11,N'Tolling Agreement',25,NULL,NULL,N'Active/Unknown',1);
GO

INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (1,1,N'ARC-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (2,1,N'ARC-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (3,1,N'ARC-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (4,2,N'ARIES-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (5,2,N'ARIES-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (6,2,N'ARIES-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (7,3,N'AZITO-01',N'Gas Turbine / Engine Train',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (8,3,N'AZITO-02',N'Generator',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (9,3,N'AZITO-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (10,4,N'BOSHOF-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (11,4,N'BOSHOF-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (12,4,N'BOSHOF-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (13,5,N'CUAMBA-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (14,5,N'CUAMBA-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (15,5,N'CUAMBA-03',N'Battery Energy Storage System',N'Storage',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (16,5,N'CUAMBA-04',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (17,6,N'DEAAR-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (18,6,N'DEAAR-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (19,6,N'DEAAR-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (20,7,N'DIBAMBA-01',N'HFO Engine Train',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (21,7,N'DIBAMBA-02',N'Generator',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (22,7,N'DIBAMBA-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (23,8,N'DROOG-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (24,8,N'DROOG-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (25,8,N'DROOG-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (26,9,N'JBAY-01',N'Turbine Fleet',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (27,9,N'JBAY-02',N'Collector System',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (28,9,N'JBAY-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (29,10,N'KLIP-01',N'Turbine Fleet',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (30,10,N'KLIP-02',N'Collector System',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (31,10,N'KLIP-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (32,11,N'KONK-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (33,11,N'KONK-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (34,11,N'KONK-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (35,12,N'KRIBI-01',N'Gas Turbine / Engine Train',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (36,12,N'KRIBI-02',N'Generator',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (37,12,N'KRIBI-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (38,13,N'MALINDI-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (39,13,N'MALINDI-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (40,13,N'MALINDI-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (41,14,N'MOCUBA-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (42,14,N'MOCUBA-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (43,14,N'MOCUBA-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (44,15,N'SONGAS-01',N'Gas Turbine / Engine Train',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (45,15,N'SONGAS-02',N'Generator',N'Electrical',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (46,15,N'SONGAS-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (47,16,N'SOUTPAN-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (48,16,N'SOUTPAN-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (49,16,N'SOUTPAN-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (50,17,N'WINNERGY-01',N'PV Array',N'Generation',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (51,17,N'WINNERGY-02',N'Inverter Fleet',N'Power Conversion',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (52,17,N'WINNERGY-03',N'Main Transformer',N'Grid Connection',N'In Service');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (53,18,N'CTT-01',N'Gas Turbine / Engine Train',N'Generation',N'Under Construction');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (54,18,N'CTT-02',N'Generator',N'Electrical',N'Under Construction');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (55,18,N'CTT-03',N'Main Transformer',N'Grid Connection',N'Under Construction');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (56,19,N'MENENGAI-01',N'Steam Turbine',N'Generation',N'Under Construction');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (57,19,N'MENENGAI-02',N'Steam Gathering System',N'Process',N'Under Construction');
INSERT INTO dw.DimAsset (AssetKey,PlantKey,AssetCode,AssetName,AssetType,AssetStatus) VALUES (58,19,N'MENENGAI-03',N'Main Transformer',N'Grid Connection',N'Under Construction');
GO

INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (1,1,1,66.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (2,2,1,11.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (3,3,3,713.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (4,4,1,66.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (5,5,1,19.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (6,5,5,7.0,N'MWh',0);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (7,6,1,50.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (8,7,4,88.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (9,8,1,50.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (10,9,2,138.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (11,10,2,27.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (12,11,1,11.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (13,12,3,216.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (14,13,1,52.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (15,14,1,41.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (16,15,3,190.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (17,16,1,31.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (18,17,1,25.0,N'MWp',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (19,18,3,450.0,N'MW',1);
INSERT INTO dw.BridgePlantTechnology (PlantTechnologyKey,PlantKey,TechnologyKey,InstalledCapacity,CapacityUnit,IsPrimary) VALUES (20,19,6,35.0,N'MW',1);
GO

INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (1,1,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (2,1,5,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (3,2,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (4,2,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (5,3,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (6,3,6,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (7,4,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (8,4,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (9,5,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (10,6,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (11,6,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (12,7,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (13,7,7,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (14,8,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (15,8,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (16,9,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (17,10,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (18,11,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (19,11,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (20,12,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (21,12,9,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (22,13,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (23,13,10,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (24,14,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (25,14,11,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (26,15,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (27,15,12,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (28,16,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (29,16,4,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (30,17,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (31,17,5,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (32,18,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (33,18,11,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (34,19,1,N'Developer / Owner / Operator',NULL,N'Brochure states Aquila role at portfolio or plant level.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (35,19,14,N'Off-taker / Counterparty',NULL,N'Agreement counterparty.');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (36,17,13,N'Co-shareholder / O&M Partner',NULL,N'Winnergy');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (37,19,15,N'Steam Supplier',NULL,N'Menengai');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (38,19,16,N'EPC Contractor',NULL,N'Menengai');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (39,19,17,N'Lender',NULL,N'Menengai');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (40,19,18,N'Lender',NULL,N'Menengai');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (41,19,19,N'Lender',NULL,N'Menengai');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (42,7,8,N'Government Co-owner',NULL,N'Dibamba');
INSERT INTO dw.BridgePlantOrganisation (PlantOrganisationKey,PlantKey,OrganisationKey,RoleType,OwnershipPercent,Notes) VALUES (43,12,8,N'Government Co-owner',NULL,N'Kribi');
GO


/*
Load the synthetic fact CSVs with your preferred ETL tool (SSIS, ADF, Fabric Data Factory,
Databricks, dbt seed, Python, or BULK INSERT). The target-column order is identical to the
corresponding CSV header.

Recommended load order:
1. fact_fx_rate_monthly.csv
2. fact_plant_operations_daily.csv
3. fact_battery_operation_daily.csv
4. fact_energy_sales_monthly.csv
5. fact_outage.csv
6. fact_maintenance_work_order.csv
7. fact_construction_progress_monthly.csv
8. fact_hse_incident.csv
*/

CREATE OR ALTER VIEW bi.vw_PortfolioOverview
AS
SELECT
    p.PlantKey,
    p.PlantCode,
    p.PlantName,
    g.CountryName,
    g.RegionName,
    p.City,
    p.Province,
    p.ProjectStatus,
    p.PrimaryTechnologyName,
    p.NameplateCapacity,
    p.CapacityUnit,
    p.StorageCapacityMWh,
    p.BrochureAnnualGenerationGWh,
    p.BrochureHomesEquivalent,
    p.BrochureCO2AvoidedTonnes
FROM dw.DimPlant p
INNER JOIN dw.DimGeography g
    ON g.GeographyKey = p.GeographyKey;
GO

CREATE OR ALTER VIEW bi.vw_DailyPlantPerformance
AS
SELECT
    d.FullDate,
    d.CalendarYear,
    d.CalendarMonthNumber,
    d.CalendarMonthName,
    d.YearMonth,
    p.PlantKey,
    p.PlantCode,
    p.PlantName,
    g.CountryName,
    g.RegionName,
    p.ProjectStatus,
    p.PrimaryTechnologyName,
    p.NameplateCapacity,
    p.CapacityUnit,
    f.GrossGenerationMWh,
    f.NetGenerationMWh,
    f.EnergyExportedMWh,
    f.AvailabilityPct,
    f.CapacityFactorPct,
    f.CurtailmentPct,
    f.PlannedDowntimeHours,
    f.ForcedDowntimeHours,
    f.Scope1EmissionsTonnesCO2e,
    f.CO2AvoidedTonnes,
    f.IsSynthetic
FROM dw.FactPlantOperationsDaily f
INNER JOIN dw.DimDate d
    ON d.DateKey = f.DateKey
INNER JOIN dw.DimPlant p
    ON p.PlantKey = f.PlantKey
INNER JOIN dw.DimGeography g
    ON g.GeographyKey = p.GeographyKey;
GO

CREATE OR ALTER VIEW bi.vw_MonthlyCommercialPerformance
AS
SELECT
    d.FullDate AS MonthStartDate,
    d.CalendarYear,
    d.CalendarMonthNumber,
    d.CalendarMonthName,
    d.YearMonth,
    p.PlantKey,
    p.PlantCode,
    p.PlantName,
    g.CountryName,
    g.RegionName,
    p.PrimaryTechnologyName,
    s.CurrencyCode,
    s.EnergySoldMWh,
    s.AverageTariffPerKWhLocal,
    s.RevenueLocalCurrency,
    s.FXRateToZAR,
    s.RevenueZAR,
    s.SettlementCollectionPct,
    s.IsSynthetic
FROM dw.FactEnergySalesMonthly s
INNER JOIN dw.DimDate d
    ON d.DateKey = s.MonthDateKey
INNER JOIN dw.DimPlant p
    ON p.PlantKey = s.PlantKey
INNER JOIN dw.DimGeography g
    ON g.GeographyKey = p.GeographyKey;
GO

CREATE OR ALTER VIEW bi.vw_MaintenanceReliability
AS
WITH OutageSummary AS
(
    SELECT
        PlantKey,
        COUNT_BIG(*) AS OutageCount,
        SUM(DurationHours) AS TotalOutageHours,
        SUM(EstimatedEnergyLostMWh) AS EstimatedEnergyLostMWh,
        SUM(CASE WHEN OutageType = N'Forced' THEN 1 ELSE 0 END) AS ForcedOutageCount
    FROM dw.FactOutage
    GROUP BY PlantKey
),
WorkOrderSummary AS
(
    SELECT
        PlantKey,
        COUNT_BIG(*) AS WorkOrderCount,
        SUM(CASE WHEN WorkOrderStatus IN (N'Open',N'In Progress') THEN 1 ELSE 0 END) AS OpenWorkOrderCount,
        SUM(TotalMaintenanceCostZAR) AS TotalMaintenanceCostZAR,
        AVG(CASE WHEN ClosedDate IS NOT NULL THEN DATEDIFF(DAY, OpenedDate, ClosedDate) * 1.0 END) AS AverageDaysToClose
    FROM dw.FactMaintenanceWorkOrder
    GROUP BY PlantKey
)
SELECT
    p.PlantKey,
    p.PlantCode,
    p.PlantName,
    g.CountryName,
    p.PrimaryTechnologyName,
    ISNULL(o.OutageCount,0) AS OutageCount,
    ISNULL(o.ForcedOutageCount,0) AS ForcedOutageCount,
    ISNULL(o.TotalOutageHours,0) AS TotalOutageHours,
    ISNULL(o.EstimatedEnergyLostMWh,0) AS EstimatedEnergyLostMWh,
    ISNULL(w.WorkOrderCount,0) AS WorkOrderCount,
    ISNULL(w.OpenWorkOrderCount,0) AS OpenWorkOrderCount,
    ISNULL(w.TotalMaintenanceCostZAR,0) AS TotalMaintenanceCostZAR,
    w.AverageDaysToClose
FROM dw.DimPlant p
INNER JOIN dw.DimGeography g
    ON g.GeographyKey = p.GeographyKey
LEFT JOIN OutageSummary o
    ON o.PlantKey = p.PlantKey
LEFT JOIN WorkOrderSummary w
    ON w.PlantKey = p.PlantKey;
GO

CREATE INDEX IX_FactPlantOperationsDaily_PlantDate
    ON dw.FactPlantOperationsDaily (PlantKey, DateKey)
    INCLUDE (EnergyExportedMWh, AvailabilityPct, CapacityFactorPct, CurtailmentPct);
GO

CREATE INDEX IX_FactEnergySalesMonthly_PlantMonth
    ON dw.FactEnergySalesMonthly (PlantKey, MonthDateKey)
    INCLUDE (EnergySoldMWh, RevenueZAR, SettlementCollectionPct);
GO

CREATE INDEX IX_FactOutage_PlantStart
    ON dw.FactOutage (PlantKey, OutageStartDateTime)
    INCLUDE (OutageType, DurationHours, EstimatedEnergyLostMWh);
GO

CREATE INDEX IX_FactMaintenanceWorkOrder_PlantStatus
    ON dw.FactMaintenanceWorkOrder (PlantKey, WorkOrderStatus)
    INCLUDE (OpenedDate, ClosedDate, Priority, TotalMaintenanceCostZAR);
GO
