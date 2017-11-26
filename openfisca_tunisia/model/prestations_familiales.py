# -*- coding: utf-8 -*-


from __future__ import division

from numpy import (
    round, zeros, maximum as max_, minimum as min_, logical_xor as xor_, logical_not as not_,
    asanyarray, amin, amax, arange)

from openfisca_tunisia.model.base import *  # noqa analysis:ignore


CHEF = QUIFOY['vous']
PART = QUIFOY['conj']

PACS = [QUIMEN['enf' + str(i)] for i in range(1, 10)]
ENFS = [QUIMEN['enf' + str(i)] for i in range(1, 10)]


def age_en_mois_benjamin(age_en_mois):
    '''
    Renvoi un vecteur (une entree pour chaque famille) avec l'age du benjamin.
    '''
    age_en_mois_benjamin = 12 * 9999
    for age_en_mois in age_en_moiss.itervalues():
        isbenjamin = (age_en_mois < age_en_mois_benjamin) * (age_en_mois >= 0)
        age_en_mois_benjamin = isbenjamin * age_en_mois + \
            not_(isbenjamin) * age_en_mois_benjamin
    return age_en_mois_benjamin


def age_min(age, minimal_age=None):
    '''
    Returns minimal age higher than or equal to a
    '''
    if minimal_age is None:
        minimal_age = 0
    ages = asanyarray(age)
    ages = ages + (ages < minimal_age) * 9999
    return amin(ages, axis=1)


def age_max(age):
    '''
    Returns minimal age higher than or equal to a
    '''
    ages = asanyarray(age)
    return amax(ages, axis=1)


def ages_first_kids(age, nb=None):
    '''
    Returns the ages of the nb first born kids according to age
    '''
    ages = asanyarray(age.values())

    ages = (ages.T + .00001 * arange(ages.shape[0])).T  # To deal with twins

    if nb is None:
        nb = 3  # TODO: 4e enfant qui en bénéficiait en 1989
    i = 0
    age_list = []

    while i < 4:
        from numpy import putmask
        maximas = amax(ages, axis=0)
        age_list.append(round(maximas))
        putmask(ages, ages == maximas, -99999)
        i += 1
    return age_list


class smig75(Variable):
    column = BoolCol
    entity = Individu
    label = u"Indicatrice de salaire supérieur à 75% du smig"
    definition_period = YEAR

    def formula(individu, period, parameters):
        salaire_imposable = individu('salaire_imposable', period = period)
        salaire_en_nature = individu('salaire_en_nature', period = period)
        smig = simulation.parameters(period.start).cotisations_sociales.gen.smig
        return (salaire_imposable + salaire_en_nature) < smig


class salaire_unique(Variable):
    column = BoolCol
    entity = Menage
    label = u"Indicatrice de salaire unique"
    definition_period = YEAR

    def formula(individu, period):
        salaire_imposable_personne_de_reference = menage.personne_de_reference('salaire_imposable', period = period)
        salaire_imposable_conjoint = menage.conjoint('salaire_imposable', period = period)
        return xor_(salaire_imposable_personne_de_reference > 0, salaire_imposable_conjoint > 0)


# Allocations familiales

class af_nbenf(Variable):
    column = FloatCol
    entity = Menage
    label = u"Nombre d'enfants au sens des allocations familiales"
    definition_period = YEAR

    def formula(individu, period, parameters):
        age_holder = menage.members('age', period = period)
        smig75_holder = menage.members('smig75', period = period)
        ivalide_holder = menage.members('invalide', period = period)

        #    From http://www.allocationfamiliale.com/allocationsfamiliales/allocationsfamilialestunisie.htm
        #    Jusqu'à l'âge de 16 ans sans conditions.
        #    Jusqu'à l'âge de 18 ans pour les enfants en apprentissage qui ne perçoivent pas une rémunération
        # supérieure à 75 % du SMIG.
        #    Jusqu'à l'âge de 21 ans pour les enfants qui fréquentent régulièrement un établissement secondaire,
        # supérieur, technique ou professionnel, à condition que les enfants n'occupent pas d'emplois salariés.
        #    Jusqu'à l'âge de 21 ans pour la jeune fille qui remplace sa mère auprès de ses frères et sœurs. TODO
        #    Sans limite d'âge et quelque soit leur rang pour les enfants atteints d'une infirmité ou d'une maladie
        # incurable et se trouvant, de ce fait, dans l'impossibilité permanente et absolue d'exercer un travail
        # lucratif, et pour les handicapés titulaires d'une carte d'handicapé qui ne sont pas pris en charge
        # intégralement par un organisme public ou privé benéficiant de l'aide de l'Etat ou des collectivités
        # locales.

        age = self.split_by_roles(age_holder, roles=ENFS)
        smig75 = self.split_by_roles(smig75_holder, roles=ENFS)
        invalide = self.split_by_roles(ivalide_holder, roles=ENFS)

        ages = ages_first_kids(age, nb=3)
        res = zeros(ages[0].shape)

        for ag in ages:
            res += (ag >= 0) * (
                (1 * (ag < 16) + 1 * (ag < 18) + 1 * (ag < 21)) >= 1)
    # (ag < 18) + # *smig75[key]*(activite[key] =='aprenti')  + # TODO apprenti
    # (ag < 21) # *(or_(activite[key]=='eleve', activite[key]=='etudiant'))
    #                 )  > 1

        return res


class af(Variable):
    column = FloatCol
    entity = Menage
    label = u"Allocations familiales"
    definition_period = YEAR

    def formula(menage, period, parameters):
        af_nbenf = menage('af_nbenf', period = period)
        salaire_imposable_holder = simulation.compute('salaire_imposable', period = period)
        _P = simulation.parameters(period.start)

        # Le montant trimestriel est calculé en pourcentage de la rémunération globale trimestrielle palfonnée
        # à 122 dinars
        # TODO: ajouter éligibilité des parents aux allocations familiales
        salaire_imposable = self.split_by_roles(
            salaire_imposable_holder, roles=[CHEF, PART])
        P = _P.prestations_familiales
        bm = min_(
            max_(salaire_imposable[CHEF], salaire_imposable[PART]) / 4, P.af.plaf_trim)  # base trimestrielle
        # prestations familliales  # Règle d'arrondi ?
        af_1enf = round(bm * P.af.taux.enf1, 2)
        af_2enf = round(bm * P.af.taux.enf2, 2)
        af_3enf = round(bm * P.af.taux.enf3, 2)
        af_base = (af_nbenf >= 1) * af_1enf + \
            (af_nbenf >= 2) * af_2enf + (af_nbenf >= 3) * af_3enf
        return 4 * af_base  # annualisé


class majoration_salaire_unique(Variable):
    column = FloatCol
    entity = Menage
    label = u"Majoration du salaire unique"
    definition_period = YEAR  # TODO trimestrialiser

    def formula(menage, period, parameters):
        salaire_unique = menage('salaire_unique', period = period)
        af_nbenf = menage('af_nbenf', period = period)
        P = parameters(period.start).prestations_familiales
        af_1enf = round(P.salaire_unique.enf1, 3)  # trimestrielle
        af_2enf = round(P.salaire_unique.enf2, 3)  # trimestrielle
        af_3enf = round(P.salaire_unique.enf3, 3)  # trimestrielle
        af = (af_nbenf >= 1) * af_1enf + (af_nbenf >= 2) * \
            af_2enf + (af_nbenf >= 3) * af_3enf
        return 4 * af * salaire_unique  # annualisé


def _af_cong_naiss(age, _P):
    # _option={'age': ENFS}
    return 0


def _af_cong_jeun_trav(age, _P):
    #    Les salariés de moins de 18 ans du régime non agricole bénéficient de
    #    2 jours de congés par mois et au maximum 24 jours ouvrables,
    #    l'employeur se fera rembourser par la CNSS 12 jours de congés. Les
    #    salariés âgés de 18 à 20 ans bénéficient de 18 jours de congés
    #    ouvrables par an soit 6 jours remboursés à l'employeur par la CNSS.
    #    Le remboursement à l'employeur est effectué par la Caisse Nationale
    #    de Sécurité Sociale de l'avance faite en exécution de l'article 113
    #    alinéa 2 du Code du Travail.
    # , _option = {'age': ENFS}
    return 0


class contribution_frais_creche(Variable):
    column = FloatCol
    entity = Menage
    label = u"Contribution aux frais de crêche"
    definition_period = YEAR

    def formula(individu, period, parameters):
        salaire_imposable_holder = menage('salaire_imposable', period = period)
        age_en_mois_holder = menage('age_en_mois', period = period)
        smig48 = parameters(period.start).cotisations_sociales.gen.smig  # TODO: smig 48H
        # TODO rework and test
        # Une prise en charge peut être accordée à la mère exerçant une
        # activité salariée et dont le salaire ne dépasse pas deux fois et demie
        # le SMIG pour 48 heures de travail par semaine. Cette contribution est
        # versée pour les enfants ouvrant droit aux prestations familiales et
        # dont l'âge est compris entre 2 et 36 mois. Elle s'élève à 15 dinars par
        # enfant et par mois pendant 11 mois.
        # , _option = {'age_en_mois': ENFS, 'sal': [CHEF, PART]}
        somme_salaire_imposable = (
            menage.personne_de_reference('salaire_imposable', period = period) +
            menage.conjoint('salaire_imposable', period = period)
            )
        age_en_mois = menage.members('age_en_mois')
        P = _P.prestations_familiales.creche
        age_m_benj = age_en_mois_benjamin(age_en_mois)
        elig_age = (age_m_benj <= P.age_max) * (age_m_benj >= P.age_min)
        elig_sal = somme_salaire_imposable < P.plaf * smig48
        return P.montant * elig_age * elig_sal * min_(P.duree, 12 - age_m_benj)


class prestations_familiales(Variable):  # TODO add _af_cong_naiss, af_cong_jeun_trav
    column = FloatCol
    entity = Menage
    label = u"Prestations familales"
    definition_period = YEAR

    def formula(menage, period):
        af = menage('af', period = period)
        majoration_salaire_unique = menage('majoration_salaire_unique', period = period)
        contribution_frais_creche = menage('contribution_frais_creche', period = period)
        return af + majoration_salaire_unique + contribution_frais_creche


#
# Assurances sociales   Maladie
#

def _as_mal(age, sal, _P):
    '''
    Assurance sociale - prestation en espèces TODO: à compléter
    '''
    # , _option = {'age': ENFS}
    #    P = _P.as.maladie
    P = 0
    mal = 0
    smig = _P.gen.smig
    return mal * P.part * max(P.plaf_mult * smig, sal) * P.duree


def _as_maternite(age, sal, _P):
    '''
    Assurance sociale - maternité  TODO: à compléter
    '''
    # P = _P.as.maternite
    smig = _P.gen.smig
    # return P.part*max(P.plaf_mult*smig,sal)*P.duree
    return 0


def _as_deces(sal, _P):
    '''
    Assurance sociale - décès   # TODO: à compléter
    '''
    # P = _P.as.deces
    return 0
